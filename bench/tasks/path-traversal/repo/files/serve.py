from pathlib import Path

PUBLIC = Path(__file__).parent / "public"


def read_public_file(name):
    """Contents of a file under public/."""
    return (PUBLIC / name).read_bytes()
