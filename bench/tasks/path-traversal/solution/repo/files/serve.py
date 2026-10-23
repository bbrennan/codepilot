from pathlib import Path

PUBLIC = (Path(__file__).parent / "public").resolve()


def read_public_file(name):
    """Contents of a file under public/."""
    target = (PUBLIC / name).resolve()
    if not target.is_relative_to(PUBLIC):
        raise PermissionError(f"{name!r} is outside public/")
    return target.read_bytes()
