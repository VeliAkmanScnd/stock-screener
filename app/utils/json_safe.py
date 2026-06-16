"""Convert numpy/pandas scalars to JSON-serializable Python types."""

from __future__ import annotations

from typing import Any

import numpy as np


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        v = float(value)
        return None if v != v else v
    if isinstance(value, float):
        return None if value != value else value
    if isinstance(value, (np.str_, str)):
        return str(value)
    return value
