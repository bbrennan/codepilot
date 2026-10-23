from reports.export import export_csv


def test_returns_count(tmp_path):
    assert export_csv([{"a": 1}], tmp_path / "x.csv") == 1
