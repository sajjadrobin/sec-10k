FROM python:3.11-slim

# Install Poetry
RUN pip install poetry==2.5.1

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-root

# Install Playwright Chromium and all its system dependencies
RUN playwright install chromium --with-deps

# Copy application code
COPY sec_fetcher/ ./sec_fetcher/
COPY company_tickers.json main.py ./

# PDFs are written here — mount a volume to persist them across restarts
RUN mkdir -p output

EXPOSE 8000

CMD ["uvicorn", "sec_fetcher.api:app", "--host", "0.0.0.0", "--port", "8000"]
