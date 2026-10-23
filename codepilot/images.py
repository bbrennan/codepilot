"""Images in the conversation: pasted or dropped in chat, linked by URL, given as a local path, or opened by
the model with view_image.

An image is stored in a message as a Converse-shaped block, {"image": {"format": "png", "source": {"bytes":
...}}}, and each provider translates it (Anthropic and Bedrock natively; OpenAI as a data URL; Ollama in
"images"). A copy goes to ~/.codepilot/images/<sha1>.<format> so the UI can show it by URL.
"""

from __future__ import annotations

import hashlib
import re
import urllib.request
from pathlib import Path

FORMATS = ("png", "jpeg", "gif", "webp")
MIME = {"png": "image/png", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
MAX_BYTES = 3_750_000  # Bedrock's per-image limit; the strictest of the providers
MAX_PER_MESSAGE = 8
TOKENS_PER_IMAGE = 1600  # a typical screenshot after the provider's downscaling; used for context estimates
EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
LOCAL_PATH = re.compile(r"(?<![\w@/])((?:~|/)[^\s<>\"'`]*\.(?:png|jpe?g|gif|webp))\b", re.I)


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
    req = urllib.request.Request(url, headers={"User-Agent": "codepilot (image fetch)", "Accept": "image/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - the user's own link
            data = resp.read(MAX_BYTES + 1)
    except OSError as exc:
        raise ImageError(f"couldn't download it: {exc}") from None
    if len(data) > MAX_BYTES:
        raise ImageError(f"image is larger than {MAX_BYTES / 1e6:.2f} MB")
    return data


def load_path(path: Path) -> bytes:
    try:
        if path.stat().st_size > MAX_BYTES:
            raise ImageError(f"{path.name} is larger than {MAX_BYTES / 1e6:.2f} MB")
        return path.read_bytes()
    except OSError as exc:
        raise ImageError(f"couldn't read {path}: {exc.strerror or exc}") from None


def from_message(text: str, root: Path | None) -> tuple[list[tuple[dict, str]], list[str]]:
    """Images the user pointed at in a message: image links, local image paths, and @-referenced images in the
    workspace. Returns ([(block, source)], [problems])."""
    found: list[tuple[dict, str]] = []
    problems: list[str] = []
    seen: set[str] = set()

    def add(source: str, loader) -> None:
        if source in seen or len(found) >= MAX_PER_MESSAGE:
            return
        seen.add(source)
        try:
            found.append((block(loader()), source))
        except ImageError as exc:
            problems.append(f"{source}: {exc}")

    for url in URL.findall(text):
        url = url.rstrip(".,;:!?")
        if url.lower().split("?")[0].endswith(EXTENSIONS) or re.search(r"\.(png|jpe?g|gif|webp)(\?|$)", url, re.I):
            add(url, lambda u=url: fetch(u))
    for raw in LOCAL_PATH.findall(text):
        path = Path(raw).expanduser()
        if path.is_file():
            add(str(path), lambda p=path: load_path(p))
    if root is not None:
        for rel in re.findall(r"(?<![\w@`])@([\w.\-/~]+\.(?:png|jpe?g|gif|webp))\b", text, re.I):
            path = (root / rel).resolve()
            if (root in path.parents) and path.is_file():
                add("@" + rel, lambda p=path: load_path(p))
    return found, problems


def is_image_name(name: str) -> bool:
    return name.lower().endswith(EXTENSIONS)
