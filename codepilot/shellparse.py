"""Reading a shell command line the way the shell would: which programs it actually runs.

Approval checks need this, because what matters is rarely the first word: `cd x && rm -rf y`, `sudo pip install z`.
"""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath

PUNCTUATION = "();<>|&\n"
SEPARATORS = set(";|&()\n")
PREFIXES = {"sudo", "command", "time", "nohup", "env", "exec", "nice", "xargs"}  # run the command after them


def segments(command: str) -> list[tuple[list[str], bool]]:
    """The simple commands in a command line, each with whether its input is piped from the one before.
    Raises ValueError on input a shell couldn't parse either (an unbalanced quote)."""
    lexer = shlex.shlex(command.replace("`", ";"), posix=True, punctuation_chars=PUNCTUATION)
    lexer.whitespace, lexer.commenters = " \t\r", ""
    lexer.whitespace_split = True
    segments, current, piped = [], [], False
    for token in lexer:
        if set(token) <= set(PUNCTUATION) and set(token) & SEPARATORS:  # redirections stay with their command
            if current:
                segments.append((current, piped))
            current, piped = [], token == "|"
        elif not set(token) <= set(PUNCTUATION):
            current.append(token)
    if current:
        segments.append((current, piped))
    return segments


def commands(tokens: list[str]) -> list[list[str]]:
    """What this simple command runs, with the program as a bare name (so /bin/rm is rm).

    Behind a wrapper (sudo, env, uv run, ...) that's every place the wrapped command could start: their options take
    values that differ per wrapper and per version, and an extra warning costs less than a missed rm -rf. One pass
    over the positions, not recursion: a long chain of wrappers must not multiply the work.
    """
    commands, starts, seen = [], [0], set()
    while starts:
        i = starts.pop()
        if i in seen:
            continue
        seen.add(i)
        while i < len(tokens) and re.match(r"^\w+=", tokens[i]):
            i += 1
        if i >= len(tokens):
            continue
        program = PurePosixPath(tokens[i]).name
        skip = 2 if program in ("uv", "poetry") and tokens[i + 1:i + 2] == ["run"] else 1 if program in PREFIXES else 0
        if skip:
            starts += [j for j in range(i + skip, len(tokens)) if j not in seen and not tokens[j].startswith("-")]
        else:
            commands.append(i)
    return [_named(tokens[i:]) for i in sorted(set(commands))]


def _named(tokens: list[str]) -> list[str]:
    tokens = [PurePosixPath(tokens[0]).name, *tokens[1:]]
    if tokens[0] == "git":
        while len(tokens) > 2 and tokens[1] in ("-C", "-c", "--no-pager"):
            del tokens[1:3 if tokens[1] != "--no-pager" else 2]
    return tokens


def simple_commands(command: str) -> list[list[str]]:
    """Every command this line runs, each as [program, args...]. [] if it can't be parsed."""
    try:
        return [c for tokens, _ in segments(command) for c in commands(tokens)]
    except ValueError:
        return []
