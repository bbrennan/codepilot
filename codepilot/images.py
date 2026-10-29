"""Images in the conversation: pasted or dropped in chat, linked by URL, given as a local path, or opened by
the model with view_image.

An image is stored in a message as a Converse-shaped block, {"image": {"format": "png", "source": {"bytes":
...}}}, and each provider translates it (Anthropic and Bedrock natively; OpenAI as a data URL; Ollama in
"images"). A copy goes to ~/.codepilot/images/<sha1>.<format> so the UI can show it by URL.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

FORMATS = ("png", "jpeg", "gif", "webp")
MIME = {"png": "image/png", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
MAX_BYTES = 3_750_000  # Bedrock's per-image limit; the strictest of the providers
MAX_PER_MESSAGE = 8
TOKENS_PER_IMAGE = 1600  # a typical screenshot after the provider's downscaling; used for context estimates
MAX_SIDE = 1568  # the long side Claude reads at full detail; bigger files are shrunk to this
MAX_FILE = 60_000_000  # don't even try to read bigger files
EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic")
_EXT = r"\.(?:png|jpe?g|gif|webp|heic)"
URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
# A path from / or ~ to an image extension. It may contain spaces (macOS screenshots are named like
# "Screenshot 2026-10-25 at 3.14.15 PM.png"), so the shortest run that ends in an extension is taken.
LOCAL_PATH = re.compile(rf"(?<![\w@/])((?:~|/)[^\n<>\"'`]*?{_EXT})(?![\w])", re.I)
QUOTED_PATH = re.compile(rf"[\"'\u201c\u2018]((?:~|/)[^\"'\n\u201c\u201d\u2018\u2019]+?{_EXT})[\"'\u201d\u2019]", re.I)
REL_PATH = re.compile(rf"(?<![\w@/~.`\\])((?:[\w.\-]+/)*[\w.\-]+{_EXT})(?![\w/])", re.I)
SPACES = re.compile(r"[\s\u00a0\u2007\u2009\u202f]+")


class ImageError(ValueError):
    pass


def sniff(data: bytes) -> str | None:
    """The image format from its first bytes (never trust a file name or a server's content type)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def block(data: bytes) -> dict:
    fmt = sniff(data)
    if fmt is None:
        raise ImageError("not a PNG, JPEG, GIF or WebP image")
    if len(data) > MAX_BYTES:
        raise ImageError(f"image is {len(data) / 1e6:.1f} MB; the limit is {MAX_BYTES / 1e6:.2f} MB "
                         "(paste it into the chat instead: the UI shrinks it)")
    return {"image": {"format": fmt, "source": {"bytes": data}}}


def save(home: Path, img: dict) -> str:
    """Keep a copy for the UI; returns its URL path."""
    data, fmt = img["image"]["source"]["bytes"], img["image"]["format"]
    sha = hashlib.sha1(data).hexdigest()
    folder = home / "images"
    path = folder / f"{sha}.{fmt}"
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return f"/api/images/{sha}.{fmt}"


def cached(home: Path, name: str) -> Path | None:
    if not re.fullmatch(r"[0-9a-f]{40}\.(png|jpeg|gif|webp)", name):
        return None
    path = home / "images" / name
    return path if path.is_file() else None


def fetch(url: str, timeout: float = 15.0) -> bytes:
    """Download an image the user linked (http/https only, size-capped)."""
    if not re.match(r"https?://", url, re.I):
        raise ImageError("only http and https links can be fetched")
    from . import webtools

    try:
        webtools.check_target(url)  # never cloud-metadata / link-local addresses; redirects stay on the same site
    except webtools.WebError as exc:
        raise ImageError(str(exc)) from None
    req = urllib.request.Request(url, headers={"User-Agent": "codepilot (image fetch)", "Accept": "image/*"})
    try:
        with urllib.request.build_opener(webtools.SameHostRedirects).open(req, timeout=timeout) as resp:
            data = resp.read(MAX_BYTES + 1)
    except (OSError, webtools.WebError) as exc:
        raise ImageError(f"couldn't download it: {exc}") from None
    if len(data) > MAX_BYTES:
        raise ImageError(f"image is larger than {MAX_BYTES / 1e6:.2f} MB")
    return data


def find_file(path: Path) -> Path | None:
    """The file, or one in the same folder whose name differs only in kinds of space or in case. macOS puts a
    narrow no-break space before AM/PM in screenshot names, which nobody (and no model) types."""
    if path.is_file():
        return path
    folder = path.parent
    if not folder.is_dir():
        return None
    want = SPACES.sub(" ", path.name).casefold()
    try:
        return next((p for p in folder.iterdir() if SPACES.sub(" ", p.name).casefold() == want and p.is_file()),
                    None)
    except OSError:
        return None


def _shrink(path: Path) -> bytes | None:
    """A copy at most MAX_SIDE pixels on the long side, as PNG (or JPEG for photos), using macOS's built-in sips
    or Pillow if installed. None if neither is available."""
    with tempfile.TemporaryDirectory(prefix="codepilot-img-") as tmp:
        for fmt in ("png", "jpeg"):
            out = Path(tmp) / f"out.{fmt}"
            if sys.platform == "darwin" and shutil.which("sips"):
                proc = subprocess.run(["sips", "-Z", str(MAX_SIDE), "-s", "format", fmt, str(path), "--out", str(out)],
                                      capture_output=True, timeout=60)
                if proc.returncode != 0:
                    return None
            else:
                try:
                    from PIL import Image  # optional
                except ImportError:
                    return None
                with Image.open(path) as im:
                    im.thumbnail((MAX_SIDE, MAX_SIDE))
                    (im.convert("RGB") if fmt == "jpeg" else im).save(out, format=fmt.upper())
            data = out.read_bytes()
            if len(data) <= MAX_BYTES:
                return data
    return None


def load_path(path: Path) -> bytes:
    """An image file's bytes, ready to send: too-large or HEIC images are shrunk and converted when possible."""
    found = find_file(path)
    if found is None:
        raise ImageError(f"{path} doesn't exist")
    try:
        size = found.stat().st_size
        if size > MAX_FILE:
            raise ImageError(f"{found.name} is {size / 1e6:.0f} MB, too large to read")
        data = found.read_bytes()
    except OSError as exc:
        raise ImageError(f"couldn't read {found}: {exc.strerror or exc}") from None
    if sniff(data) and len(data) <= MAX_BYTES:
        return data
    shrunk = _shrink(found)
    if shrunk is None:
        what = "isn't a PNG, JPEG, GIF or WebP image" if not sniff(data) else f"is {len(data) / 1e6:.1f} MB"
        raise ImageError(f"{found.name} {what} and couldn't be converted here; paste it into the chat instead "
                         "(the browser shrinks it)")
    return shrunk


def _candidates(raw: str) -> list[str]:
    """A matched path, then each shorter path starting after a space inside it ("in ~/Desktop: ~/Desktop/a b.png")."""
    out = [raw]
    for i, ch in enumerate(raw[:-1]):
        if ch.isspace() and raw[i + 1] in "/~":
            out.append(raw[i + 1:])
    return out


def from_message(text: str, root: Path | None) -> tuple[list[tuple[dict, str]], list[str]]:
    """Images the user pointed at in a message: image links, local image paths (spaces allowed, quoted or not),
    workspace image paths with or without @. Returns ([(block, source)], [problems])."""
    from . import mentions

    found: list[tuple[dict, str]] = []
    problems: list[str] = []
    seen: set[str] = set()

    def add(source: str, loader, key: str = "") -> None:
        key = key or source
        if key in seen or len(found) >= MAX_PER_MESSAGE:
            return
        seen.add(key)
        try:
            found.append((block(loader()), source))
        except ImageError as exc:
            problems.append(f"{source}: {exc}")

    for url in URL.findall(text):
        url = url.rstrip(".,;:!?")
        if url.lower().split("?")[0].endswith(EXTENSIONS) or re.search(r"\.(png|jpe?g|gif|webp)(\?|$)", url, re.I):
            add(url, lambda u=url: fetch(u))
    plain = URL.sub(" ", text).replace("\\ ", " ")  # paths dragged into a terminal escape their spaces
    for raw in QUOTED_PATH.findall(plain) + LOCAL_PATH.findall(plain):
        for cand in _candidates(raw):
            path = find_file(Path(cand).expanduser())
            if path is not None:
                add(str(path), lambda p=path: load_path(p))
                break
    if root is not None:
        rels = [m["rel"] for m in mentions.find_mentions(root, plain) if is_image_name(m["rel"])]
        rels += [r for r in REL_PATH.findall(plain) if not r.startswith(("http", "www."))]
        for rel in rels:
            path = find_file((root / rel).resolve())
            if path is not None and root in path.parents:
                add("@" + str(path.relative_to(root)), lambda p=path: load_path(p), key=str(path))
    return found, problems


def is_image_name(name: str) -> bool:
    return name.lower().endswith(EXTENSIONS)
