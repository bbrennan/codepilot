import csv

from reports.export import export_csv


def read(path):
    with open(path, newline="") as fh:
        return list(csv.reader(fh))


def test_default_columns(tmp_path):
    p = tmp_path / "a.csv"
    assert export_csv([{"sku": "A", "price": 1.5}, {"sku": "B", "price": 2}], p) == 2
    assert read(p) == [["sku", "price"], ["A", "1.5"], ["B", "2"]]


def test_columns_missing_and_extra(tmp_path):
    p = tmp_path / "b.csv"
    export_csv([{"sku": "A", "name": "x", "extra": 1}, {"sku": "B"}], p, columns=["name", "sku"])
    assert read(p) == [["name", "sku"], ["x", "A"], ["", "B"]]


def test_quoting(tmp_path):
    p = tmp_path / "c.csv"
    export_csv([{"name": 'Shoes, "red"\nsize 9'}], p)
    assert read(p) == [["name"], ['Shoes, "red"\nsize 9']]


def test_empty(tmp_path):
    p = tmp_path / "d.csv"
    assert export_csv([], p) == 0
    assert p.read_text() == ""
