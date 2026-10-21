from pathlib import Path

import pytest

from sec_fetcher.api import _filter_companies, _sort_companies, _status, _lock, _ticker_status
from sec_fetcher.companies import Company

COMPANIES = [
    Company(ticker="MSFT", cik=789019, title="Microsoft Corp"),
    Company(ticker="AAPL", cik=320193, title="Apple Inc."),
    Company(ticker="GOOGL", cik=1652044, title="Alphabet Inc."),
]


# ---------------------------------------------------------------------------
# _sort_companies
# ---------------------------------------------------------------------------

def test_sort_ticker_asc():
    result = _sort_companies(COMPANIES, "ticker", "asc")
    assert [c.ticker for c in result] == ["AAPL", "GOOGL", "MSFT"]


def test_sort_ticker_desc():
    result = _sort_companies(COMPANIES, "ticker", "desc")
    assert [c.ticker for c in result] == ["MSFT", "GOOGL", "AAPL"]


def test_sort_downloaded_puts_downloaded_first(tmp_path, monkeypatch):
    pdf = tmp_path / "2025.pdf"
    pdf.write_bytes(b"fake")

    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: pdf if t == "AAPL" else None)

    result = _sort_companies(COMPANIES, "downloaded", "desc")
    assert result[0].ticker == "AAPL"


def test_sort_downloaded_puts_missing_last_regardless_of_direction(tmp_path, monkeypatch):
    pdf = tmp_path / "2025.pdf"
    pdf.write_bytes(b"fake")

    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: pdf if t == "AAPL" else None)

    for order in ("asc", "desc"):
        result = _sort_companies(COMPANIES, "downloaded", order)
        assert result[-1].ticker in ("MSFT", "GOOGL"), f"Missing PDF should be last for order={order}"


# ---------------------------------------------------------------------------
# _filter_companies
# ---------------------------------------------------------------------------

def test_filter_all(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: None)
    assert len(_filter_companies(COMPANIES, "all")) == 3


def test_filter_downloaded(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: Path("fake.pdf") if t == "AAPL" else None)
    result = _filter_companies(COMPANIES, "downloaded")
    assert [c.ticker for c in result] == ["AAPL"]


def test_filter_not_downloaded(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: Path("fake.pdf") if t == "AAPL" else None)
    result = _filter_companies(COMPANIES, "not_downloaded")
    assert len(result) == 2
    assert all(c.ticker != "AAPL" for c in result)


# ---------------------------------------------------------------------------
# _ticker_status
# ---------------------------------------------------------------------------

def test_ticker_status_missing(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: None)
    assert _ticker_status("AAPL") == {"status": "missing"}


def test_ticker_status_ready(tmp_path, monkeypatch):
    pdf = tmp_path / "2025.pdf"
    pdf.write_bytes(b"fake")
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: pdf)

    result = _ticker_status("AAPL")
    assert result["status"] == "ready"
    assert result["url"].endswith("2025.pdf")
    assert "downloaded_at" in result


def test_ticker_status_downloading(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: None)
    with _lock:
        _status["__TEST__"] = "downloading"
    try:
        assert _ticker_status("__TEST__") == {"status": "downloading"}
    finally:
        with _lock:
            del _status["__TEST__"]


def test_ticker_status_error(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: None)
    with _lock:
        _status["__TEST__"] = "error:SEC returned 500"
    try:
        result = _ticker_status("__TEST__")
        assert result["status"] == "error"
        assert result["message"] == "SEC returned 500"
    finally:
        with _lock:
            del _status["__TEST__"]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_index_pagination(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: None)
    from starlette.testclient import TestClient
    from sec_fetcher.api import app

    client = TestClient(app, raise_server_exceptions=True)

    r = client.get("/")
    assert r.status_code == 200
    assert "Showing 1–25 of 10443" in r.text

    r = client.get("/?page=2")
    assert "Showing 26–50 of 10443" in r.text


def test_index_search(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: None)
    from starlette.testclient import TestClient
    from sec_fetcher.api import app

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/?q=apple")
    assert r.status_code == 200
    assert "AAPL" in r.text


def test_index_page_clamped_to_valid_range(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: None)
    from starlette.testclient import TestClient
    from sec_fetcher.api import app

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/?page=99999")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/filings/{ticker}
# ---------------------------------------------------------------------------

def test_get_filing_unknown_ticker():
    from starlette.testclient import TestClient
    from sec_fetcher.api import app

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/api/filings/FAKE")
    assert r.status_code == 404
    assert "Unknown ticker" in r.json()["detail"]


def test_get_filing_not_downloaded(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: None)
    from starlette.testclient import TestClient
    from sec_fetcher.api import app

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/api/filings/AAPL")
    assert r.status_code == 404
    assert "POST /api/download/AAPL" in r.json()["detail"]


def test_get_filing_ready(tmp_path, monkeypatch):
    pdf = tmp_path / "2025.pdf"
    pdf.write_bytes(b"fake")
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: pdf)

    from starlette.testclient import TestClient
    from sec_fetcher.api import app

    client = TestClient(app, raise_server_exceptions=True)
    r = client.get("/api/filings/AAPL")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "AAPL"
    assert data["year"] == "2025"
    assert data["url"].endswith("2025.pdf")
    assert "downloaded_at" in data


def test_get_filing_ticker_normalised_to_uppercase(monkeypatch):
    monkeypatch.setattr("sec_fetcher.api._latest_pdf", lambda t: None)
    from starlette.testclient import TestClient
    from sec_fetcher.api import app

    client = TestClient(app, raise_server_exceptions=True)
    # lowercase ticker should work the same as uppercase
    r = client.get("/api/filings/aapl")
    assert r.status_code == 404
    assert "AAPL" in r.json()["detail"]
