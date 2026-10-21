import os
import time
import httpx

_BACKOFF_SECONDS = [2, 4, 8]
_INTER_REQUEST_DELAY = 0.5


def _build_headers() -> dict[str, str]:
    name = os.environ.get("SEC_USER_AGENT_NAME", "").strip()
    email = os.environ.get("SEC_USER_AGENT_EMAIL", "").strip()
    if not name or not email:
        raise EnvironmentError(
            "SEC_USER_AGENT_NAME and SEC_USER_AGENT_EMAIL must be set.\n"
            "Example:\n"
            "  export SEC_USER_AGENT_NAME='Jane Doe'\n"
            "  export SEC_USER_AGENT_EMAIL='jane@example.com'"
        )
    return {"User-Agent": f"{name} {email}"}


def get(url: str) -> httpx.Response:
    """GET a URL with rate limiting and exponential backoff on 429."""
    headers = _build_headers()

    for attempt, backoff in enumerate([0] + _BACKOFF_SECONDS):
        if backoff:
            print(f"  Rate limited — retrying in {backoff}s (attempt {attempt}/3)…")
            time.sleep(backoff)

        response = httpx.get(url, headers=headers, follow_redirects=True, timeout=30)

        if response.status_code == 429:
            continue

        response.raise_for_status()
        time.sleep(_INTER_REQUEST_DELAY)
        return response

    raise RuntimeError(f"Failed to fetch {url} after {len(_BACKOFF_SECONDS)} retries (429)")
