"""Package guard: judge packages before they're installed.

Code models recommend packages that don't exist, and repeat the same invented names, which is what makes registering
them worthwhile ("slopsquatting"). So what a command would install, or a manifest edit would add, is looked up in its
public registry and graded where the user decides. Only the package name leaves the machine. A failed lookup
never blocks anything, and nothing is refused: a private package is "not found" too, and that's the user's call.
"""

from __future__ import annotations

import json
import re
import threading
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import PurePosixPath

from . import shellparse

TIMEOUT = 5
CACHE_FOR, RETRY_AFTER = 3600, 60
NEW_DAYS, FEW_RELEASES = 90, 2
MAX_CHECKED = 20
REGISTRY = {"pypi": "PyPI", "npm": "npm", "crates": "crates.io"}
INSTALLERS = {("pip", "install"): "pypi", ("pip3", "install"): "pypi", ("uv", "add"): "pypi", ("poetry", "add"): "pypi",
              ("pipx", "install"): "pypi", ("npm", "install"): "npm", ("npm", "i"): "npm", ("npm", "add"): "npm",
              ("pnpm", "add"): "npm", ("yarn", "add"): "npm", ("bun", "add"): "npm", ("cargo", "add"): "crates"}
# Per ecosystem: the same flag can differ (--optional takes a value in uv, not in cargo or npm), and taking a package
# name as a flag's value would hide it from the check.
TAKES_A_VALUE = {
    "pypi": {"-r", "--requirement", "-e", "--editable", "-c", "--constraint", "-i", "--index-url", "--index",
             "--default-index", "--extra-index-url", "-f", "--find-links", "-t", "--target", "--group", "--optional",
             "-p", "--python", "--with", "--package", "--rev", "--tag", "--branch", "--path", "--directory",
             "--project", "--source", "--extras", "-E"},
    "npm": {"--registry", "--prefix", "-C", "--tag", "-w", "--workspace", "--filter", "--cache"},
    "crates": {"-F", "--features", "--git", "--branch", "--tag", "--rev", "--path", "--registry", "--rename",
               "-p", "--package", "--manifest-path", "--vers"},
}


class NotFound(Exception):
    """The registry answered: no such package."""


@dataclass
class Info:
    eco: str
    name: str
    found: bool | None  # None: couldn't check
    created: float | None
    releases: int | None


CACHE: dict[tuple[str, str], tuple[Info, float]] = {}
_lock = threading.Lock()


def _get(url: str, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "codepilot (package guard)"})  # crates.io requires one
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (fixed https registries)
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound from None
        raise


# -- what would be installed -------------------------------------------------------------------------------------


def _normalize(eco: str, name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower() if eco == "pypi" else name


def _name(eco: str, spec: str) -> str:
    """The package name in an install spec: no version, extras or markers."""
    if eco == "npm":
        m = re.match(r"(@[^/\s]+/[^@\s]+|[^@\s]+)", spec)
    elif eco == "crates":
        m = re.match(r"[^@\s]+", spec)
    else:
        m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", spec)
    return m.group(1 if eco == "npm" else 0) if m else ""


def _is_local(eco: str, spec: str) -> bool:
    if spec.startswith((".", "git+")) or "://" in spec or spec.endswith((".whl", ".tar.gz", ".zip")):
        return True
    return "/" in spec and not (eco == "npm" and spec.startswith("@"))


def _installer(cmd: list[str]) -> tuple[str, list[str]] | None:
    """(ecosystem, what follows the install subcommand), if this command installs. Global options can come first
    (`pip --isolated install x`), so the subcommand is looked for, not assumed to be the second word."""
    if cmd[0].startswith("python") and "-m" in cmd[:-1] and cmd[cmd.index("-m") + 1] == "pip":
        cmd = ["pip", *cmd[cmd.index("-m") + 2:]]
    for i, word in enumerate(cmd[1:], 1):
        if cmd[0] == "uv" and word == "pip":
            return _installer(["pip", *cmd[i + 1:]])
        if (cmd[0], word) in INSTALLERS:
            return INSTALLERS[(cmd[0], word)], cmd[i + 1:]
    return None


def _spec(spec: str) -> str:
    """What an npm alias really installs: react@npm:other@1 is `other`."""
    return spec.split("npm:", 1)[1] if "@npm:" in spec or spec.startswith("npm:") else spec


def installs(command: str) -> list[tuple[str, str]]:
    """The (ecosystem, name) pairs a shell command would install from a public registry, in every part of it."""
    found = []
    for cmd in shellparse.simple_commands(command):
        match = _installer(cmd)
        if match is None:
            continue
        eco, args = match
        i = 0
        while i < len(args):
            arg = args[i]
            if arg.startswith("-"):
                i += 2 if arg in TAKES_A_VALUE[eco] else 1
                continue
            spec = _spec(arg) if eco == "npm" else arg
            if not _is_local(eco, spec) and (name := _name(eco, spec)):
                found.append((eco, _normalize(eco, name)))
            i += 1
    return list(dict.fromkeys(found))


def _python_deps(text: str) -> list[str]:
    data = tomllib.loads(text)
    project = data.get("project", {})
    specs = list(project.get("dependencies", []))
    for group in (*project.get("optional-dependencies", {}).values(), *data.get("dependency-groups", {}).values()):
        specs += [s for s in group if isinstance(s, str)]
    names = [_name("pypi", s) for s in specs if "://" not in s]  # `x @ https://...` isn't from the registry
    poetry = data.get("tool", {}).get("poetry", {})
    for table in (poetry.get("dependencies", {}), *[g.get("dependencies", {}) for g in poetry.get("group", {}).values()]):
        names += [n for n in table if n != "python"]
    return names


def _requirements(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines()]
    return [_name("pypi", line) for line in lines if line and line[0] not in "#-" and "://" not in line]


def _npm_deps(text: str) -> list[str]:
    data = json.loads(text)
    names = []
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name, value in data.get(key, {}).items():
            value = str(value)
            if value.startswith("npm:"):  # an alias: the key is a local name, the value says what's installed
                names.append(_name("npm", _spec(value)))
            elif "/" not in value and not value.startswith(("file:", "link:", "workspace:", "git", "http")):
                names.append(name)
    return names


def _crates(text: str) -> list[str]:
    data = tomllib.loads(text)
    names = []
    for table in (data.get("dependencies", {}), data.get("dev-dependencies", {})):
        for name, value in table.items():
            if not isinstance(value, dict):
                names.append(name)
            elif not {"path", "git", "workspace"} & set(value):
                names.append(value.get("package", name))
    return names


def _reader(filename: str):
    if filename == "pyproject.toml":
        return "pypi", _python_deps
    if re.match(r"requirements.*\.txt$", filename):
        return "pypi", _requirements
    if filename == "package.json":
        return "npm", _npm_deps
    return ("crates", _crates) if filename == "Cargo.toml" else (None, None)


def added(path: str, before: str, after: str) -> list[tuple[str, str]]:
    """The (ecosystem, name) pairs a manifest edit adds. A file that doesn't parse adds nothing here: the check after
    applying reports bad TOML or JSON."""
    eco, read = _reader(PurePosixPath(path).name)
    if read is None:
        return []
    try:
        now = [_normalize(eco, n) for n in read(after)]
    except (ValueError, TypeError, AttributeError):
        return []
    try:
        was = {_normalize(eco, n) for n in read(before)}
    except (ValueError, TypeError, AttributeError):
        was = set()
    return [(eco, n) for n in dict.fromkeys(now) if n and n not in was]


# -- what the registries say ---------------------------------------------------------------------------------------


def _timestamp(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


def _parse(eco: str, name: str, body: str) -> Info:
    data = json.loads(body)
    if eco == "pypi":
        files = [f for release in data["releases"].values() for f in release]
        uploads = [_timestamp(f["upload_time_iso_8601"]) for f in files]
        releases = sum(bool(r) for r in data["releases"].values())
        return Info(eco, name, True, min(uploads) if uploads else None, releases)
    if eco == "npm":
        return Info(eco, name, True, _timestamp(data["time"]["created"]), len(data.get("versions", {})))
    return Info(eco, name, True, _timestamp(data["crate"]["created_at"]), len(data.get("versions", [])))


def _url(eco: str, name: str) -> str:
    quoted = urllib.parse.quote(name, safe="")
    return {"pypi": f"https://pypi.org/pypi/{quoted}/json", "npm": f"https://registry.npmjs.org/{quoted}",
            "crates": f"https://crates.io/api/v1/crates/{quoted}"}[eco]


def lookup(eco: str, name: str, http=None, now: float | None = None) -> Info:
    now = time.time() if now is None else now
    name = _normalize(eco, name)
    with _lock:
        hit = CACHE.get((eco, name))
    if hit and now < hit[1]:
        return hit[0]
    try:
        info = _parse(eco, name, (http or _get)(_url(eco, name), TIMEOUT))
    except NotFound:
        info = Info(eco, name, False, None, None)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, HTTPException):
        info = Info(eco, name, None, None, None)  # advisory: a bad answer is "couldn't check", never a failed call
    with _lock:
        CACHE[(eco, name)] = (info, now + (RETRY_AFTER if info.found is None else CACHE_FOR))
    return info


def verdict(info: Info, now: float) -> tuple[str, str]:
    """(danger | caution | info, what to tell the user)."""
    where = REGISTRY[info.eco]
    if info.found is None:
        return "info", f"couldn't reach {where}"
    if not info.found:
        return "danger", f"not on {where}: possibly an invented name, or a private package"
    count = f"{info.releases} release{'s' if info.releases != 1 else ''}" if info.releases is not None else ""
    if info.created is not None and now - info.created < NEW_DAYS * 86400:
        days = int((now - info.created) / 86400)
        return "caution", f"first published {days} days ago on {where}" + (f" · {count}" if count else "")
    year = datetime.fromtimestamp(info.created, timezone.utc).year if info.created is not None else None
    since = f"on {where} since {year}" if year else f"on {where}"
    text = f"{since} · {count}" if count else since
    return ("caution" if info.releases is not None and info.releases <= FEW_RELEASES else "info"), text


def check(pairs: list[tuple[str, str]], http=None, now: float | None = None) -> list[dict]:
    """One {eco, name, level, text} per package, looked up side by side."""
    now = time.time() if now is None else now
    pick = pairs[:MAX_CHECKED]
    with ThreadPoolExecutor(max_workers=4) as pool:
        infos = list(pool.map(lambda p: lookup(p[0], p[1], http, now), pick))
    lines = []
    for info in infos:
        level, text = verdict(info, now)
        lines.append({"eco": info.eco, "name": info.name, "level": level, "text": text})
    if len(pairs) > MAX_CHECKED:
        lines.append({"eco": "", "name": "", "level": "info", "text": f"{len(pairs) - MAX_CHECKED} more not checked"})
    return lines
