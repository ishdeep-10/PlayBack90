import sys
from pathlib import Path

import pytest


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


@pytest.fixture(autouse=True)
def disable_auth_by_default(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.fixture(autouse=True)
def enable_opposition_analysis_by_default(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "opposition_analysis_enabled", True)
