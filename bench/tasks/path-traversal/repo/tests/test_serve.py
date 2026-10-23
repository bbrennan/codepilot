from files.serve import read_public_file


def test_reads_public():
    assert read_public_file("index.txt") == b"hello\n"
