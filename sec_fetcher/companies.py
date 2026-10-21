import json
from dataclasses import dataclass
from pathlib import Path

TICKERS = ["AAPL", "META", "GOOGL", "AMZN", "NFLX", "GS"]

_TICKERS_FILE = Path(__file__).parent.parent / "company_tickers.json"


@dataclass
class Company:
    ticker: str
    cik: int
    title: str


def _load_all() -> list[Company]:
    with _TICKERS_FILE.open() as f:
        data = json.load(f)
    return sorted(
        (Company(ticker=e["ticker"], cik=e["cik_str"], title=e["title"]) for e in data.values()),
        key=lambda c: c.ticker,
    )


ALL_COMPANIES: list[Company] = _load_all()
_TICKER_INDEX: dict[str, Company] = {c.ticker: c for c in ALL_COMPANIES}


def load_all_companies() -> list[Company]:
    return ALL_COMPANIES


def load_companies() -> list[Company]:
    """Return Company objects for the target tickers."""
    missing = [t for t in TICKERS if t not in _TICKER_INDEX]
    if missing:
        raise ValueError(f"Tickers not found in company_tickers.json: {missing}")
    return [_TICKER_INDEX[t] for t in TICKERS]


def load_cik_map() -> dict[str, int]:
    return {c.ticker: c.cik for c in load_companies()}
