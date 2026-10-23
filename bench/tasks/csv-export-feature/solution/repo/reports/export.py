import csv


def export_csv(rows, path, columns=None):
    """Write `rows` (a list of dicts) to a CSV file at `path`."""
    columns = list(columns) if columns else (list(rows[0]) if rows else [])
    with open(path, "w", newline="") as fh:
        if not columns:
            return 0
        writer = csv.DictWriter(fh, fieldnames=columns, restval="", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
