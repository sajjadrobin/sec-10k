import threading
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .companies import load_all_companies, Company
from .converter import html_to_pdf
from .filing import get_latest_10k
from . import client, metadata

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI()
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")

_status: dict[str, str] = {}
_lock = threading.Lock()

PAGE_SIZE = 25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_pdf(ticker: str) -> Path | None:
    base = OUTPUT_DIR / ticker / "10-K"
    if not base.exists():
        return None
    pdfs = sorted(base.glob("*.pdf"), reverse=True)
    return pdfs[0] if pdfs else None


def _ticker_status(ticker: str) -> dict:
    pdf = _latest_pdf(ticker)
    with _lock:
        state = _status.get(ticker)

    if pdf:
        mtime = pdf.stat().st_mtime
        downloaded_at = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        return {"status": "ready", "url": f"/output/{ticker}/10-K/{pdf.name}", "downloaded_at": downloaded_at, "mtime": mtime}
    if state == "downloading":
        return {"status": "downloading"}
    if state and state.startswith("error:"):
        return {"status": "error", "message": state[6:]}
    return {"status": "missing"}


def _run_download(ticker: str, cik: int) -> None:
    try:
        checked_at = datetime.now()
        filing = get_latest_10k(ticker, cik)
        output_path = OUTPUT_DIR / ticker / "10-K" / f"{filing.fiscal_year}.pdf"
        if not output_path.exists():
            response = client.get(filing.document_url)
            html_to_pdf(response.text, filing.document_url, output_path)
        metadata.write(filing, output_path, checked_at)
        with _lock:
            _status[ticker] = "done"
    except Exception as e:
        with _lock:
            _status[ticker] = f"error:{e}"


def _filter_companies(companies: list[Company], filter_by: str) -> list[Company]:
    if filter_by == "downloaded":
        return [c for c in companies if _latest_pdf(c.ticker) is not None]
    if filter_by == "not_downloaded":
        return [c for c in companies if _latest_pdf(c.ticker) is None]
    return companies


def _sort_companies(companies: list[Company], sort: str, order: str) -> list[Company]:
    reverse = order == "desc"

    if sort == "downloaded":
        def key(c: Company):
            pdf = _latest_pdf(c.ticker)
            if not pdf:
                return (1, 0)  # always last, regardless of direction
            mtime = pdf.stat().st_mtime
            return (0, -mtime if reverse else mtime)
        return sorted(companies, key=key)  # no reverse — handled in key

    # Default: sort by ticker
    return sorted(companies, key=lambda c: c.ticker, reverse=reverse)


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _render_row(c: Company) -> str:
    ticker = c.ticker
    s = _ticker_status(ticker)
    status = s["status"]

    if status == "ready":
        badge = '<span class="badge badge-ready">Ready</span>'
        time_cell = s["downloaded_at"]
        action = f'<a class="btn btn-view" href="{s["url"]}" target="_blank">View PDF</a>'
    elif status == "downloading":
        badge = '<span class="badge badge-downloading"><span class="spinner"></span>Downloading…</span>'
        time_cell = "—"
        action = '<button class="btn btn-download" disabled>Downloading…</button>'
    elif status == "error":
        msg = s.get("message", "").replace('"', "&quot;")
        badge = f'<span class="badge badge-error" title="{msg}">Error</span>'
        time_cell = "—"
        action = f'<button class="btn btn-download" onclick="startDownload(\'{ticker}\')">Retry</button>'
    else:
        badge = '<span class="badge badge-missing">Not downloaded</span>'
        time_cell = "—"
        action = f'<button class="btn btn-download" onclick="startDownload(\'{ticker}\')">Download</button>'

    return f"""
      <tr id="row-{ticker}">
        <td class="ticker">{ticker}</td>
        <td>{c.title}</td>
        <td id="status-{ticker}">{badge}</td>
        <td id="time-{ticker}">{time_cell}</td>
        <td id="action-{ticker}">{action}</td>
      </tr>"""


def _render_page(companies: list[Company], page: int, total: int, query: str, sort: str, order: str, filter_by: str) -> str:
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    rows = "".join(_render_row(c) for c in companies)

    def qs(p: int = page, q: str = query, s: str = sort, o: str = order, f: str = filter_by) -> str:
        parts = [f"page={p}"]
        if q:
            parts.append(f"q={q}")
        if s:
            parts.append(f"sort={s}")
        if o:
            parts.append(f"order={o}")
        if f and f != "all":
            parts.append(f"filter={f}")
        return "?" + "&".join(parts)

    def sort_link(col: str, label: str) -> str:
        if sort == col:
            new_order = "asc" if order == "desc" else "desc"
            arrow = " ↑" if order == "asc" else " ↓"
            return f'<a class="sort-link active" href="{qs(p=1, s=col, o=new_order)}">{label}{arrow}</a>'
        return f'<a class="sort-link" href="{qs(p=1, s=col, o="asc")}">{label} <span class="sort-neutral">⇅</span></a>'

    def page_link(p: int, label: str, disabled: bool = False) -> str:
        if disabled:
            return f'<span class="page-btn disabled">{label}</span>'
        return f'<a class="page-btn" href="{qs(p=p)}">{label}</a>'

    nav_items = [page_link(page - 1, "← Prev", disabled=(page <= 1))]
    for p in range(max(1, page - 2), min(total_pages, page + 2) + 1):
        if p == page:
            nav_items.append(f'<span class="page-btn active">{p}</span>')
        else:
            nav_items.append(f'<a class="page-btn" href="{qs(p=p)}">{p}</a>')
    nav_items.append(page_link(page + 1, "Next →", disabled=(page >= total_pages)))
    nav_items.append(
        f'<form onsubmit="goToPage(event,{total_pages})" style="display:flex;align-items:center;gap:0.35rem;margin-left:0.5rem;">'
        f'<input id="goto-input" type="number" min="1" max="{total_pages}" placeholder="Page" '
        f'style="width:60px;padding:0.35rem 0.5rem;border:1px solid #d1d1d6;border-radius:8px;font-size:0.85rem;outline:none;" />'
        f'<button type="submit" class="page-btn" style="cursor:pointer;">Go</button>'
        f'</form>'
    )
    nav_html = "".join(nav_items)

    start = (page - 1) * PAGE_SIZE + 1
    end = min(page * PAGE_SIZE, total)
    q_val = query.replace('"', "&quot;")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SEC 10-K Filings</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f5f7; color: #1d1d1f; padding: 2rem;
    }}
    header {{ margin-bottom: 1.5rem; }}
    header h1 {{ font-size: 1.5rem; font-weight: 600; }}
    header p {{ color: #6e6e73; margin-top: 0.25rem; font-size: 0.9rem; }}
    .toolbar {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }}
    .search-wrap {{ position: relative; flex: 0 0 320px; }}
    .search-wrap input {{
      width: 100%; padding: 0.5rem 0.75rem 0.5rem 2.25rem;
      border: 1px solid #d1d1d6; border-radius: 8px; font-size: 0.9rem;
      background: #fff; outline: none;
    }}
    .search-wrap input:focus {{ border-color: #0071e3; }}
    .search-icon {{
      position: absolute; left: 0.65rem; top: 50%; transform: translateY(-50%);
      color: #6e6e73; font-size: 0.85rem; pointer-events: none;
    }}
    .count {{ color: #6e6e73; font-size: 0.85rem; margin-left: auto; }}
    table {{
      width: 100%; border-collapse: collapse; background: #fff;
      border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}
    th {{
      text-align: left; padding: 0.75rem 1.25rem; font-size: 0.75rem;
      font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
      color: #6e6e73; background: #fafafa; border-bottom: 1px solid #e5e5ea;
    }}
    .sort-neutral {{ color: #c0c0c8; font-size: 0.7rem; }}
    .sort-link:hover .sort-neutral {{ color: #6e6e73; }}
    .sort-link {{
      text-decoration: none; color: #6e6e73;
    }}
    .sort-link:hover {{ color: #1d1d1f; }}
    .sort-link.active {{ color: #0071e3; }}
    td {{
      padding: 0.85rem 1.25rem; border-bottom: 1px solid #f2f2f7;
      font-size: 0.9rem; vertical-align: middle;
    }}
    tr:last-child td {{ border-bottom: none; }}
    .ticker {{ font-weight: 600; font-family: "SF Mono", "Fira Code", monospace; font-size: 0.85rem; }}
    .badge {{
      display: inline-block; padding: 0.2rem 0.6rem;
      border-radius: 20px; font-size: 0.75rem; font-weight: 500;
    }}
    .badge-ready       {{ background: #d1fae5; color: #065f46; }}
    .badge-missing     {{ background: #f3f4f6; color: #6b7280; }}
    .badge-downloading {{ background: #dbeafe; color: #1e40af; }}
    .badge-error       {{ background: #fee2e2; color: #991b1b; }}
    .btn {{
      display: inline-block; padding: 0.4rem 1rem; border-radius: 8px;
      font-size: 0.85rem; font-weight: 500; cursor: pointer; border: none; text-decoration: none;
    }}
    .btn-download {{ background: #0071e3; color: #fff; }}
    .btn-download:hover {{ background: #0077ed; }}
    .btn-download:disabled {{ background: #b0c4de; cursor: not-allowed; }}
    .btn-view {{ background: #f2f2f7; color: #0071e3; }}
    .btn-view:hover {{ background: #e5e5ea; }}
    .spinner {{
      display: inline-block; width: 14px; height: 14px;
      border: 2px solid #bfdbfe; border-top-color: #1e40af;
      border-radius: 50%; animation: spin 0.7s linear infinite;
      vertical-align: middle; margin-right: 0.4rem;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .pagination {{
      display: flex; align-items: center; gap: 0.4rem;
      justify-content: center; margin-top: 1.5rem;
    }}
    .page-btn {{
      display: inline-block; padding: 0.4rem 0.75rem; border-radius: 8px;
      font-size: 0.85rem; text-decoration: none; color: #1d1d1f;
      background: #fff; border: 1px solid #d1d1d6;
    }}
    .page-btn:hover {{ background: #f2f2f7; }}
    .page-btn.active {{ background: #0071e3; color: #fff; border-color: #0071e3; font-weight: 600; }}
    .page-btn.disabled {{ color: #b0b0b8; pointer-events: none; background: #fafafa; }}
    .filter-select {{
      padding: 0.5rem 0.75rem; border: 1px solid #d1d1d6; border-radius: 8px;
      font-size: 0.9rem; background: #fff; color: #1d1d1f; outline: none; cursor: pointer;
    }}
    .filter-select:focus {{ border-color: #0071e3; }}
  </style>
</head>
<body>
  <header>
    <h1>SEC 10-K Filings</h1>
    <p>Browse and download annual reports from SEC EDGAR</p>
  </header>

  <div class="toolbar">
    <form class="search-wrap" method="get" action="/">
      <span class="search-icon">🔍</span>
      <input
        type="text" name="q" value="{q_val}"
        placeholder="Search ticker or company…"
        oninput="this.form.submit()"
      />
      <input type="hidden" name="page" value="1" />
      <input type="hidden" name="sort" value="{sort}" />
      <input type="hidden" name="order" value="{order}" />
      <input type="hidden" name="filter" value="{filter_by}" />
    </form>
    <select class="filter-select" onchange="applyFilter(this.value)">
      <option value="all" {'selected' if filter_by == 'all' else ''}>All</option>
      <option value="downloaded" {'selected' if filter_by == 'downloaded' else ''}>Downloaded</option>
      <option value="not_downloaded" {'selected' if filter_by == 'not_downloaded' else ''}>Not Downloaded</option>
    </select>
    <div class="pagination" style="margin:0;">{nav_html}</div>
    <span class="count">Showing {start}–{end} of {total}</span>
  </div>

  <table>
    <thead>
      <tr>
        <th>{sort_link("ticker", "Ticker")}</th>
        <th>Company</th>
        <th>Status</th>
        <th>{sort_link("downloaded", "Last Downloaded")}</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

  <div class="pagination">{nav_html}</div>

  <script>
    function goToPage(e, totalPages) {{
      e.preventDefault();
      const input = document.getElementById("goto-input");
      const p = Math.max(1, Math.min(parseInt(input.value), totalPages));
      if (!isNaN(p)) {{
        const url = new URL(window.location);
        url.searchParams.set("page", p);
        window.location = url;
      }}
    }}

    function applyFilter(value) {{
      const url = new URL(window.location);
      url.searchParams.set("filter", value);
      url.searchParams.set("page", "1");
      window.location = url;
    }}

    const polling = new Set();

    function startDownload(ticker) {{
      fetch(`/api/download/${{ticker}}`, {{ method: "POST" }})
        .then(() => {{ setDownloading(ticker); pollStatus(ticker); }});
    }}

    function setDownloading(ticker) {{
      document.getElementById(`status-${{ticker}}`).innerHTML =
        `<span class="badge badge-downloading"><span class="spinner"></span>Downloading…</span>`;
      document.getElementById(`action-${{ticker}}`).innerHTML =
        `<button class="btn btn-download" disabled>Downloading…</button>`;
      document.getElementById(`time-${{ticker}}`).textContent = "—";
    }}

    function pollStatus(ticker) {{
      if (polling.has(ticker)) return;
      polling.add(ticker);
      const interval = setInterval(() => {{
        fetch(`/api/status/${{ticker}}`).then(r => r.json()).then(data => {{
          if (data.status === "downloading") return;
          clearInterval(interval);
          polling.delete(ticker);
          if (data.status === "ready") {{
            document.getElementById(`status-${{ticker}}`).innerHTML =
              `<span class="badge badge-ready">Ready</span>`;
            document.getElementById(`time-${{ticker}}`).textContent = data.downloaded_at;
            document.getElementById(`action-${{ticker}}`).innerHTML =
              `<a class="btn btn-view" href="${{data.url}}" target="_blank">View PDF</a>`;
          }} else if (data.status === "error") {{
            document.getElementById(`status-${{ticker}}`).innerHTML =
              `<span class="badge badge-error" title="${{data.message}}">Error</span>`;
            document.getElementById(`action-${{ticker}}`).innerHTML =
              `<button class="btn btn-download" onclick="startDownload('${{ticker}}')">Retry</button>`;
          }}
        }});
      }}, 2000);
    }}

    document.querySelectorAll("[id^='status-']").forEach(el => {{
      if (el.querySelector(".spinner")) {{
        pollStatus(el.id.replace("status-", ""));
      }}
    }});
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(page: int = 1, q: str = "", sort: str = "ticker", order: str = "asc", filter: str = "all"):
    if sort not in ("ticker", "downloaded"):
        sort = "ticker"
    if order not in ("asc", "desc"):
        order = "asc"
    if filter not in ("all", "downloaded", "not_downloaded"):
        filter = "all"

    companies = load_all_companies()

    if q:
        q_lower = q.lower()
        companies = [c for c in companies if q_lower in c.ticker.lower() or q_lower in c.title.lower()]

    companies = _filter_companies(companies, filter)
    companies = _sort_companies(companies, sort, order)

    total = len(companies)
    page = max(1, min(page, max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)))
    page_companies = companies[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    return HTMLResponse(_render_page(page_companies, page, total, q, sort, order, filter))


@app.get("/api/filings/{ticker}")
def get_filing(ticker: str):
    """Return the path and metadata of the latest downloaded 10-K for a ticker.

    Returns 404 if the ticker is unknown or the filing has not been downloaded yet.
    """
    ticker = ticker.upper()

    cik_map = {c.ticker: c.cik for c in load_all_companies()}
    if ticker not in cik_map:
        raise HTTPException(status_code=404, detail=f"Unknown ticker '{ticker}'.")

    pdf = _latest_pdf(ticker)
    if pdf is None:
        raise HTTPException(
            status_code=404,
            detail=f"No 10-K filing found for '{ticker}'. "
                   f"Use POST /api/download/{ticker} to fetch it.",
        )

    meta = metadata.read(pdf)
    return {
        "ticker": ticker,
        "url": f"/output/{ticker}/10-K/{pdf.name}",
        "year": pdf.stem,
        "downloaded_at": datetime.fromtimestamp(pdf.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        **(meta or {}),
    }


@app.get("/api/status/{ticker}")
def status(ticker: str):
    return _ticker_status(ticker)


@app.post("/api/download/{ticker}")
def download(ticker: str, background_tasks: BackgroundTasks):
    with _lock:
        if _status.get(ticker) == "downloading":
            return {"message": "already in progress"}
        _status[ticker] = "downloading"

    cik_map = {c.ticker: c.cik for c in load_all_companies()}
    if ticker not in cik_map:
        with _lock:
            del _status[ticker]
        return {"message": f"unknown ticker {ticker}"}

    background_tasks.add_task(_run_download, ticker, cik_map[ticker])
    return {"message": "started"}
