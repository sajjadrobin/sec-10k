import os
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: marks tests that call the real SEC API and Playwright (slow)"
    )


@pytest.fixture(autouse=True)
def require_user_agent(request):
    """Skip integration tests if SEC env vars are not set."""
    if request.node.get_closest_marker("integration"):
        if not os.environ.get("SEC_USER_AGENT_NAME") or not os.environ.get("SEC_USER_AGENT_EMAIL"):
            pytest.skip("SEC_USER_AGENT_NAME and SEC_USER_AGENT_EMAIL must be set to run integration tests")
