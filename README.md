# SEC 10-K Fetcher

Fetches the latest 10-K annual reports from SEC EDGAR for a set of companies and saves them as PDFs.

**Companies:** Apple, Meta, Alphabet, Amazon, Netflix, Goldman Sachs

---

## Running with Docker (recommended)

No local Python setup needed — Docker handles everything.

### With Docker Compose

```bash
export SEC_USER_AGENT_NAME="Your Name"
export SEC_USER_AGENT_EMAIL="you@example.com"

docker compose up --build
```

### With Docker only

```bash
# Build the image
docker build -t sec-fetcher .

# Run the container
docker run -p 8000:8000 \
  -e SEC_USER_AGENT_NAME="Your Name" \
  -e SEC_USER_AGENT_EMAIL="you@example.com" \
  -v $(pwd)/output:/app/output \
  sec-fetcher
```

Then open [http://localhost:8000](http://localhost:8000).

Downloaded PDFs are written to `./output/` on the host and persist across restarts.

---

## Running locally

### Requirements

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)

### Install Poetry

```bash
curl -sSL https://install.python-poetry.org | python3 -

# Add Poetry to your PATH (add this to ~/.zshrc or ~/.bashrc to make it permanent)
export PATH="$HOME/.local/bin:$PATH"
```

### Setup

```bash
# Install dependencies
poetry install

# Install headless Chromium (one-time, required for PDF conversion)
poetry run playwright install chromium

# Set your contact details (required by SEC fair-use policy)
export SEC_USER_AGENT_NAME="Your Name"
export SEC_USER_AGENT_EMAIL="you@example.com"
```

### Run

**Web UI** — browse filings and trigger downloads from the browser:
```bash
poetry run uvicorn sec_fetcher.api:app --port 8000
```
Then open [http://localhost:8000](http://localhost:8000).

**CLI** — download all filings headlessly:
```bash
poetry run python main.py
```

---

## Testing

### Unit tests

Fast, no network or browser required:

```bash
poetry run pytest
```

### Integration tests

Hit the real SEC API and render PDFs with Chromium (~17s). Requires the env vars to be set:

```bash
export SEC_USER_AGENT_NAME="Your Name"
export SEC_USER_AGENT_EMAIL="you@example.com"

poetry run pytest -m integration
```

### Run all tests

```bash
poetry run pytest -m ""
```

---

## Output structure

PDFs are saved to `output/{TICKER}/10-K/{year}.pdf`:

```
output/
├── AAPL/
│   └── 10-K/
│       └── 2025.pdf
├── META/
│   └── 10-K/
│       └── 2026.pdf
...
```

Re-running skips filings that have already been downloaded.
