from dataclasses import dataclass
from . import client

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}"


@dataclass
class Filing:
    ticker: str
    cik: int
    accession_no: str   # with dashes, e.g. "0000320193-24-000123"
    fiscal_year: str    # e.g. "2024"
    filing_date: str    # full date, e.g. "2024-11-01"
    document_url: str


def get_latest_10k(ticker: str, cik: int) -> Filing:
    """Fetch filing metadata for the most recent 10-K for a given company."""
    padded_cik = str(cik).zfill(10)
    url = _SUBMISSIONS_URL.format(cik=padded_cik)
    data = client.get(url).json()

    filings = data["filings"]["recent"]
    forms = filings["form"]
    accessions = filings["accessionNumber"]
    dates = filings["filingDate"]
    primary_docs = filings["primaryDocument"]

    for i, form in enumerate(forms):
        if form == "10-K":
            accession_no = accessions[i]          # "0000320193-24-000123"
            accession_path = accession_no.replace("-", "")  # "000032019324000123"
            filename = primary_docs[i]
            fiscal_year = dates[i][:4]            # "2024-11-01" → "2024"

            document_url = _ARCHIVE_BASE.format(
                cik=cik,
                accession=accession_path,
                filename=filename,
            )

            return Filing(
                ticker=ticker,
                cik=cik,
                accession_no=accession_no,
                fiscal_year=fiscal_year,
                filing_date=dates[i],
                document_url=document_url,
            )

    raise ValueError(f"No 10-K filing found for {ticker} (CIK {cik})")
