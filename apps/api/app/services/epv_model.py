"""Production EPV scoring helpers.

EPV v1 is a deterministic grid-based scorer. It does not load a trained model,
but it follows the same service shape as the other modeled metrics so live
imports, preprocessing, and backfills can share one path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


STREAMLIT_ROOT = Path(__file__).resolve().parents[4]
if str(STREAMLIT_ROOT) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_ROOT))

from Data.epv_features import (  # noqa: E402
    DEFAULT_EPV_VERSION,
    build_epv_columns,
    summarize_epv_quality,
)


def apply_epv_values(
    events: pd.DataFrame,
    version: str = DEFAULT_EPV_VERSION,
    artifact_dir: str | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Return an event dataframe with EPV columns updated."""

    return build_epv_columns(events, version=version, artifact_dir=artifact_dir, force=force)


def epv_quality_summary(events: pd.DataFrame) -> dict[str, object]:
    """Return a compact EPV scoring summary for QA."""

    return summarize_epv_quality(events)
