import pytest

from files.serve import PUBLIC, read_public_file


def test_nested_ok():
    assert read_public_file("img/logo.txt") == b"logo\n"


@pytest.mark.parametrize("name", ["../secrets.txt", "img/../../secrets.txt", "../public_backup/secret.txt",
                                  str(PUBLIC.parent / "secrets.txt")])
def test_blocked(name):
    with pytest.raises(PermissionError):
        read_public_file(name)
