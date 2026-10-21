import shutil
from pathlib import Path

import pytest

# Use NFLX — smaller 10-K than most, faster to download and convert
TICKER = "NFLX"


@pytest.fixture(autouse=True)
def clean_output():
    """Remove the test ticker's output before and after each test."""
    path = Path("output") / TICKER
    shutil.rmtree(path, ignore_errors=True)
    yield
    shutil.rmtree(path, ignore_errors=True)


@pytest.mark.integration
def test_run_download_creates_pdf():
    from sec_fetcher.api import _run_download, _latest_pdf
    from sec_fetcher.companies import load_cik_map

    _run_download(TICKER, load_cik_map()[TICKER])

    pdf = _latest_pdf(TICKER)
    assert pdf is not None, "PDF file was not created"
    assert pdf.exists()
    assert pdf.stat().st_size > 0, "PDF file is empty"
    assert pdf.suffix == ".pdf"


@pytest.mark.integration
def test_run_download_idempotent():
    """Re-running download should not overwrite an existing PDF."""
    from sec_fetcher.api import _run_download, _latest_pdf
    from sec_fetcher.companies import load_cik_map

    cik = load_cik_map()[TICKER]

    _run_download(TICKER, cik)
    mtime_first = _latest_pdf(TICKER).stat().st_mtime

    _run_download(TICKER, cik)
    mtime_second = _latest_pdf(TICKER).stat().st_mtime

    assert mtime_first == mtime_second, "PDF was re-downloaded on second run"


@pytest.mark.integration
def test_download_api_endpoint():
    """POST /api/download triggers a background task that produces a PDF."""
    from starlette.testclient import TestClient
    from sec_fetcher.api import app, _latest_pdf

    with TestClient(app) as client:
        r = client.post(f"/api/download/{TICKER}")
        assert r.status_code == 200
        assert r.json()["message"] in ("started", "already in progress")

    # Background tasks run when the TestClient context exits
    pdf = _latest_pdf(TICKER)
    assert pdf is not None and pdf.exists()


@pytest.mark.integration
def test_status_endpoint_reflects_ready_after_download():
    """GET /api/status returns 'ready' with a URL once the PDF exists."""
    from starlette.testclient import TestClient
    from sec_fetcher.api import app, _run_download
    from sec_fetcher.companies import load_cik_map

    _run_download(TICKER, load_cik_map()[TICKER])

    client = TestClient(app)
    data = client.get(f"/api/status/{TICKER}").json()

    assert data["status"] == "ready"
    assert data["url"].startswith(f"/output/{TICKER}/")
    assert "downloaded_at" in data
