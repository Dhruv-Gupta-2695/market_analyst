"""Thin HTTP client the Streamlit UI uses to call the FastAPI backend."""

import httpx
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# A full analysis runs several LLM calls behind a 5 requests/minute limiter (plus retries on
# Gemini 503s) on a free-tier backend, so 60s was too short. Connect stays short to fail fast.
TIMEOUT = httpx.Timeout(240.0, connect=30.0)


def analyze(query: str) -> dict:
    logger.info("Calling POST /analyze query=%r", query)
    response = httpx.post(f"{settings.backend_url}/analyze", json={"query": query}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def portfolio(holdings: dict[str, float]) -> dict:
    logger.info("Calling POST /portfolio holdings=%s", holdings)
    payload = {"holdings": [{"ticker": ticker, "qty": qty} for ticker, qty in holdings.items()]}
    response = httpx.post(f"{settings.backend_url}/portfolio", json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def compare(tickers: list[str]) -> dict:
    logger.info("Calling POST /compare tickers=%s", tickers)
    response = httpx.post(f"{settings.backend_url}/compare", json={"tickers": tickers}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()
