from __future__ import annotations

from typing import Any


def dataframe_to_records(obj: Any, max_rows: int | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        import pandas as pd

        if isinstance(obj, pd.DataFrame):
            df = obj.copy()
            df = df.where(pd.notna(df), None)
            if max_rows is not None:
                df = df.head(max_rows)
            return df.to_dict(orient="records"), [str(c) for c in df.columns]
    except Exception:
        pass
    if isinstance(obj, list):
        rows = obj[:max_rows] if max_rows is not None else obj
        columns = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
        return rows, columns
    if isinstance(obj, dict):
        return [obj], list(obj.keys())
    return [{"value": str(obj)}], ["value"]


def row_count(obj: Any) -> int | None:
    try:
        import pandas as pd

        if isinstance(obj, pd.DataFrame):
            return int(len(obj))
    except Exception:
        pass
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict):
        return 1
    return None
