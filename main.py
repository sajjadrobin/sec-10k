from datetime import datetime
from pathlib import Path
from sec_fetcher.companies import load_cik_map
from sec_fetcher.filing import get_latest_10k
from sec_fetcher import client, metadata
from sec_fetcher.converter import html_to_pdf

OUTPUT_DIR = Path("output")


def process_company(ticker: str, cik: int) -> None:
    print(f"[{ticker}] Resolving latest 10-K…")
    checked_at = datetime.now()
    filing = get_latest_10k(ticker, cik)

    output_path = OUTPUT_DIR / ticker / "10-K" / f"{filing.fiscal_year}.pdf"

    if output_path.exists():
        print(f"[{ticker}] Already downloaded ({output_path}), skipping.")
        return

    print(f"[{ticker}] Downloading {filing.document_url}…")
    response = client.get(filing.document_url)

    print(f"[{ticker}] Converting to PDF…")
    html_to_pdf(
        html_content=response.text,
        base_url=filing.document_url,
        output_path=output_path,
    )

    metadata.write(filing, output_path, checked_at)
    print(f"[{ticker}] Saved → {output_path}")


def main() -> None:
    cik_map = load_cik_map()

    errors: list[str] = []
    for ticker, cik in cik_map.items():
        try:
            process_company(ticker, cik)
        except Exception as e:
            print(f"[{ticker}] ERROR: {e}")
            errors.append(ticker)

    print()
    if errors:
        print(f"Completed with errors for: {', '.join(errors)}")
    else:
        print("All filings downloaded successfully.")


if __name__ == "__main__":
    main()
