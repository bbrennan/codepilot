def export_csv(rows, path, columns=None):
    """Write `rows` (a list of dicts) to a CSV file at `path`.

    - The first line is a header. Columns default to the keys of the first row, in order; pass
      `columns` to choose and order them.
    - Missing keys are written as empty fields; extra keys are ignored.
    - Values containing commas, quotes or newlines must be quoted correctly (standard CSV).
    - With no rows and no columns, write an empty file.
    - Returns the number of data rows written.
    """
    raise NotImplementedError
