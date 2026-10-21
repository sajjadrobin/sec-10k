import json
from datetime import datetime
from pathlib import Path

from .filing import Filing


def write(filing: Filing, pdf_path: Path, checked_at: datetime) -> None:
    """Write a metadata.json file alongside the PDF recording filing lineage."""
    meta = {
        "ticker": filing.ticker,
        "cik": filing.cik,
        "accession_no": filing.accession_no,
        "filing_date": filing.filing_date,
        "source_url": filing.document_url,
        "checked_at": checked_at.strftime("%Y-%m-%d %H:%M"),
        "downloaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    meta_path = pdf_path.with_suffix(".metadata.json")
    meta_path.write_text(json.dumps(meta, indent=2))


def read(pdf_path: Path) -> dict | None:
    """Return the metadata for a PDF, or None if the metadata file does not exist."""
    meta_path = pdf_path.with_suffix(".metadata.json")
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text())
