"""Resolve company names / free-text tickers to Yahoo Finance symbols for Indian equities."""

import yfinance as yf

from app.agents.schemas import TickerGuessOutput
from app.core.llm import get_llm, get_rate_limiter
from app.core.logging import get_logger
from app.prompts.symbol_guess import build_symbol_guess_messages

# The curated map lives in a dependency-free module so the Streamlit UI can import it without
# loading yfinance / the LLM client. Re-exported here so existing imports keep working.
from app.tools.symbol_map import NIFTY50_SYMBOLS  # noqa: F401

logger = get_logger(__name__)


def resolve_symbol(company_name: str) -> str | None:
    """Resolve a free-text company name or ticker to a Yahoo Finance symbol.

    Order: curated map -> direct ticker validation (.NS then .BO) -> LLM best-guess + validation.
    Returns None if nothing resolves.
    """
    key = company_name.strip().lower()
    if key in NIFTY50_SYMBOLS:
        symbol = NIFTY50_SYMBOLS[key]
        logger.info("Resolved '%s' -> '%s' via curated map", company_name, symbol)
        return symbol

    if _looks_like_ticker(company_name):
        symbol = _validate_with_suffixes(company_name.strip().upper())
        if symbol:
            logger.info("Resolved '%s' -> '%s' via direct ticker validation", company_name, symbol)
            return symbol

    symbol = _resolve_via_llm(company_name)
    if symbol:
        logger.info("Resolved '%s' -> '%s' via LLM guess + validation", company_name, symbol)
        return symbol

    logger.warning("Could not resolve ticker for '%s'", company_name)
    return None


def _resolve_via_llm(company_name: str) -> str | None:
    """Last-resort fallback: ask the LLM for a best-guess ticker, then verify it via yfinance.

    Never trusts the LLM's guess blindly, and never raises — any failure here just means
    resolution falls through to the caller's "could not resolve" path.
    """
    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(TickerGuessOutput)
        get_rate_limiter().acquire()
        guess: TickerGuessOutput = structured_llm.invoke(build_symbol_guess_messages(company_name))
    except Exception as exc:
        logger.warning("LLM ticker resolution failed for '%s': %s", company_name, exc)
        return None

    if not guess.ticker:
        return None

    return _validate_with_suffixes(guess.ticker.strip().upper())


def _validate_with_suffixes(base: str) -> str | None:
    for suffix in (".NS", ".BO"):
        candidate = base if base.endswith(suffix) else f"{base}{suffix}"
        if _validate_ticker(candidate):
            return candidate
    return None


def _looks_like_ticker(text: str) -> bool:
    stripped = text.strip().replace("&", "").replace(".", "")
    return bool(stripped) and stripped.isalnum() and " " not in text.strip() and len(stripped) <= 20


def _validate_ticker(symbol: str) -> bool:
    try:
        fast_info = yf.Ticker(symbol).fast_info
        last_price = fast_info.get("lastPrice") if hasattr(fast_info, "get") else None
        return last_price is not None
    except Exception as exc:
        logger.debug("Ticker validation failed for '%s': %s", symbol, exc)
        return False
