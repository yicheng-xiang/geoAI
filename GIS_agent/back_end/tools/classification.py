import numpy as np
import pandas as pd


def quantile_breaks(values, requested_classes):
    """Return ascending quantile upper bounds with duplicate bounds removed."""
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if numeric.empty:
        return []
    class_count = max(1, min(int(requested_classes), int(numeric.nunique())))
    probabilities = np.linspace(1 / class_count, 1, class_count)
    bounds = np.quantile(numeric.to_numpy(dtype=float), probabilities)
    result = []
    for bound in bounds:
        value = float(bound)
        if not result or value > result[-1]:
            result.append(value)
    maximum = float(numeric.max())
    if not result or result[-1] < maximum:
        result.append(maximum)
    return result
