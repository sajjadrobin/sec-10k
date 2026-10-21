# SPEC: SEC 10-K Report Fetcher

## Objective
A Python CLI service that fetches the latest 10-K annual reports from SEC EDGAR for a set of
companies and saves them as PDF files. Designed as the foundation of an internal Quartr service
that exposes filing documents to other teams.

**Target users:** Internal Quartr engineers / data consumers.

---

## Companies

Target tickers (hardcoded in `companies.py`):
`AAPL`, `META`, `GOOGL`, `AMZN`, `NFLX`, `GS`

CIK numbers are **not hardcoded** — they are resolved at runtime by looking up each ticker in
`company_tickers.json` (the SEC's full company ticker file, bundled with the project).

File format: `{ "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, … }`

The lookup builds an index `{ ticker → cik_str }` once on startup and uses it for all companies.

---

## Core Flow

1. **Resolve latest 10-K filing** — call `https://data.sec.gov/submissions/CIK{cik}.json`,
   scan the `filings.recent` arrays for the most recent entry where `form == "10-K"`.
2. **Build document URL** — construct the EDGAR archive URL from the accession number and
   the primary document filename.
3. **Download the HTML document** — stream the filing HTML from `https://www.sec.gov/Archives/…`
4. **Convert to PDF** — render the HTML to PDF with `weasyprint`.
5. **Save output** — write `output/{ticker}/10-K/{fiscal_year}.pdf`.

---

## Project Structure

```
quartr/
├── sec_fetcher/
│   ├── __init__.py
│   ├── client.py           # SEC EDGAR HTTP client (rate-limited)
│   ├── filing.py           # Resolve latest 10-K filing metadata
│   ├── converter.py        # HTML → PDF conversion
│   └── companies.py        # Target ticker list + CIK lookup from JSON
├── company_tickers.json    # SEC full company/ticker/CIK file (provided)
├── main.py                 # CLI entry point
├── pyproject.toml
└── README.md
```

---

## Tech Stack

- **Language:** Python 3.11+
- **Package manager:** Poetry (`pyproject.toml`)
- **HTTP:** `httpx` (async-capable, good streaming support)
- **PDF conversion:** `playwright` (headless Chromium) — better rendering for complex SEC HTML
- **CLI:** stdlib `argparse` or plain `__main__`
- **Rate limiting:** respect SEC fair-use policy — max 10 req/s, `User-Agent` header required

---

## SEC API Details

- Submissions endpoint: `https://data.sec.gov/submissions/CIK{10-digit-zero-padded-cik}.json`
- Filing index: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K`
- Archive base: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{filename}`
- Required header: `User-Agent: {name} {email}` — read from env vars `SEC_USER_AGENT_NAME` and
  `SEC_USER_AGENT_EMAIL`. Use your own personal name and email; SEC just needs a real contact,
  not a company name. Script exits with a clear error if either var is unset.

---

## Rate Limiting

- Fixed `0.5s` sleep after every API call (keeps us at ~2 req/s, well under SEC's 10 req/s limit)
- On HTTP 429: exponential backoff — retry after `2^attempt` seconds (2s, 4s, 8s), max 3 retries
- After 3 failed retries: log error and skip to next company
- All rate-limit logic lives in `client.py`; callers never handle it

## Idempotency

- Before downloading, check if `output/{ticker}/10-K/{year}.pdf` already exists — if so, skip
- Writes go to a `.tmp` file first, then renamed atomically to `.pdf` on completion
- A crashed mid-write leaves a `.tmp` but no `.pdf`, so the next run correctly re-downloads

---

## Acceptance Criteria

- [ ] Running `python main.py` produces one PDF per company under `output/{ticker}/10-K/{year}.pdf`
- [ ] Each PDF is the **most recent** 10-K (not any older filing)
- [ ] Re-running the script skips already-downloaded filings
- [ ] Script handles HTTP errors gracefully (logs and continues to next company)
- [ ] Respects SEC rate limits (no 429s)
- [ ] README explains how to install dependencies and run the script

---

## Boundaries

| Category    | Rule |
|-------------|------|
| Always do   | Set `User-Agent` from env vars `SEC_USER_AGENT_NAME` / `SEC_USER_AGENT_EMAIL` — never hardcode |
| Always do   | Zero-pad CIK to 10 digits before calling submissions API |
| Never do    | Store credentials or PII |
| Never do    | Hammer the API — add a small delay between requests |
| Out of scope | Auth, databases, scheduling, exposing an HTTP API |
