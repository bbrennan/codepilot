"""A file's text exactly as it is on disk, line endings included.

Python's text mode reads "\\r\\n" as "\\n" and writes "\\n" back, so a change applied that way rewrote every line of a
Windows-style file (git showed the whole file changed), and Undo couldn't put back the bytes it replaced. Here the
text is kept as it is. The model's text, which it read with "\\n" line endings, is matched and written in the file's
own line endings, and everything the change doesn't touch keeps its bytes, even in a file with mixed line endings.
"""

from __future__ import annotations

from pathlib import Path


def read(path: Path, errors: str = "strict") -> str:
    return path.read_bytes().decode("utf-8", errors)


def write(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def is_crlf(text: str) -> bool:
    """Most of its line breaks are "\\r\\n"."""
    crlf = text.count("\r\n")
    return crlf > 0 and crlf * 2 >= text.count("\n")


def like(text: str, file_text: str) -> str:
    """`text` in the line endings of `file_text`."""
    return lf(text).replace("\n", "\r\n") if is_crlf(file_text) else text


def find(content: str, old: str, new: str) -> tuple[int, str | None]:
    """How often `old` occurs in `content`, and `content` with `new` in its place if exactly once. Both are tried in
    the file's line endings first, then as given (an edit to the "\\n" part of a mixed file)."""
    forms = [(like(old, content), like(new, content))]
    if forms[0][0] != old:
        forms.append((old, new))
    for o, n in forms:
        count = content.count(o)
        if count:
            return count, content.replace(o, n, 1) if count == 1 else None
    return 0, None
