"""Smoke-test every dashboard page headlessly against the real prepared data.

Skipped automatically if the processed datasets have not been generated.
"""

from pathlib import Path

import pytest

from src.data.load import processed_available

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "pages").glob("*.py"), key=lambda p: int(p.name.split("_")[0]))

pytestmark = pytest.mark.skipif(not processed_available(), reason="processed data not prepared")


@pytest.mark.parametrize("page", PAGES, ids=[p.stem for p in PAGES])
def test_page_renders_without_exception(page):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    at.run()
    assert not at.exception, at.exception
    at.switch_page(f"pages/{page.name}")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("pea-header" in m.value for m in at.markdown), "page header not rendered"


def test_season_filter_empty_state():
    """A narrow filter must produce explained states, not crashes."""
    import datetime as dt

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    at.session_state["f_seasons"] = ["Monsoon"]
    at.session_state["f_dates"] = (dt.date(2024, 7, 1), dt.date(2024, 7, 31))
    for page in PAGES:
        at.switch_page(f"pages/{page.name}")
        at.run()
        assert not at.exception, (page.name, [e.value for e in at.exception])
