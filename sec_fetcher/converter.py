import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright


def html_to_pdf(html_content: str, base_url: str, output_path: Path) -> None:
    """Convert an HTML string to PDF using headless Chromium, writing atomically via a .tmp file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(".tmp")

    # Write HTML to a temp file so Chromium can resolve relative URLs via file://
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(html_content)
        tmp_html = Path(f.name)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(tmp_html.as_uri(), wait_until="networkidle")
            page.pdf(path=str(tmp_path), format="A4", print_background=True)
            browser.close()
    finally:
        tmp_html.unlink(missing_ok=True)

    tmp_path.rename(output_path)
