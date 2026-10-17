"""Streamlit UI: ask about a stock, compare two stocks, or track a portfolio."""

import sys
from pathlib import Path

# `streamlit run` adds this file's directory to sys.path automatically, but other
# entrypoints (e.g. AppTest in tests) don't — so make the sibling import robust either way.
sys.path.insert(0, str(Path(__file__).parent))

# Local dev installs `app` (backend/app) as a package via `pip install -e .`, but some hosts
# (e.g. Streamlit Community Cloud, whose installer skips building this repo as its own package -
# see pyproject.toml's `[tool.poetry] package-mode = false`) never do that. Adding backend/
# directly to sys.path makes `app.*` importable either way.
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import api_client
import streamlit as st
from app.core.logging import get_logger
from app.tools.symbol_map import NIFTY50_SYMBOLS  # light module: avoids loading yfinance / the LLM client

logger = get_logger(__name__)

st.set_page_config(page_title="Market Analyst", page_icon="📈", layout="wide")

TICKER_OPTIONS = sorted(set(NIFTY50_SYMBOLS.values()))


def _ticker_label(ticker: str) -> str:
    return ticker.replace(".NS", "").replace(".BO", "")


def render_result(result: dict) -> None:
    errors = result.get("errors") or []
    if errors:
        st.warning("Some data could not be retrieved:\n\n" + "\n".join(f"- {e}" for e in errors))

    verdict = result.get("verdict")
    if verdict and verdict.get("recommendation"):
        confidence = verdict.get("confidence")
        confidence_text = f" (confidence: {confidence:.0%})" if confidence is not None else ""
        st.success(f"**Verdict: {verdict['recommendation']}**{confidence_text}")

    st.markdown(result.get("final_answer", ""))

    findings = result.get("findings", {})
    labels = {
        "fundamental": "Fundamental Analysis",
        "technical": "Technical Analysis",
        "sentiment": "Sentiment Analysis",
    }
    for key, label in labels.items():
        items = findings.get(key) or []
        if not items:
            continue
        with st.expander(label):
            for item in items:
                st.markdown(f"**{item['ticker']}** — score: {item['score']:+.2f}")
                st.write(item["summary"])
                for point in item.get("key_points", []):
                    st.markdown(f"- {point}")


def _init_state() -> None:
    st.session_state.setdefault("holdings", {})


def render_sidebar() -> None:
    st.sidebar.header("My Portfolio")

    with st.sidebar.form("add_holding_form", clear_on_submit=True):
        ticker = st.selectbox(
            "Company", options=TICKER_OPTIONS, format_func=_ticker_label, key="holding_ticker"
        )
        custom_ticker = st.text_input("Or a custom ticker (e.g. ZOMATO.NS)", key="holding_custom_ticker")
        qty = st.number_input("Quantity", min_value=0.0, step=1.0, value=1.0, key="holding_qty")
        submitted = st.form_submit_button("Add holding")
        if submitted:
            resolved = custom_ticker.strip().upper() or ticker
            st.session_state.holdings[resolved] = qty
            logger.info("Added holding %s qty=%s", resolved, qty)

    if st.session_state.holdings:
        st.sidebar.write("**Holdings:**")
        for ticker, qty in list(st.session_state.holdings.items()):
            cols = st.sidebar.columns([3, 2, 1])
            cols[0].write(ticker)
            cols[1].write(qty)
            if cols[2].button("✕", key=f"remove_{ticker}"):
                del st.session_state.holdings[ticker]
                st.rerun()

    portfolio_clicked = st.sidebar.button(
        "How is my portfolio doing?", key="portfolio_button", disabled=not st.session_state.holdings
    )
    if portfolio_clicked:
        with st.spinner("Analyzing your portfolio..."):
            try:
                st.session_state["portfolio_result"] = api_client.portfolio(st.session_state.holdings)
            except Exception as exc:
                logger.exception("Portfolio analysis failed")
                st.sidebar.error(f"Failed to analyze portfolio: {exc}")


def render_ask_tab() -> None:
    query = st.text_input(
        "Ask about any Indian stock", placeholder="How is Reliance doing?", key="ask_query"
    )
    if st.button("Analyze", key="analyze_button") and query.strip():
        with st.spinner("Analyzing..."):
            try:
                st.session_state["analyze_result"] = api_client.analyze(query)
            except Exception as exc:
                logger.exception("Analyze request failed")
                st.error(f"Failed to analyze: {exc}")

    if st.session_state.get("analyze_result"):
        render_result(st.session_state["analyze_result"])


def render_compare_tab() -> None:
    col1, col2 = st.columns(2)
    ticker_a = col1.selectbox(
        "Stock A", options=TICKER_OPTIONS, format_func=_ticker_label, key="compare_a"
    )
    ticker_b = col2.selectbox(
        "Stock B", options=TICKER_OPTIONS, format_func=_ticker_label, index=1, key="compare_b"
    )

    if st.button("Compare", key="compare_button"):
        if ticker_a == ticker_b:
            st.warning("Pick two different stocks to compare.")
        else:
            with st.spinner("Comparing..."):
                try:
                    st.session_state["compare_result"] = api_client.compare([ticker_a, ticker_b])
                except Exception as exc:
                    logger.exception("Compare request failed")
                    st.error(f"Failed to compare: {exc}")

    if st.session_state.get("compare_result"):
        render_result(st.session_state["compare_result"])


def main() -> None:
    _init_state()
    st.title("📈 Market Analyst")
    st.caption("Multi-agent fundamental + technical + sentiment analysis for Indian equities.")

    render_sidebar()

    if st.session_state.get("portfolio_result"):
        st.subheader("Portfolio Overview")
        render_result(st.session_state["portfolio_result"])
        st.divider()

    ask_tab, compare_tab = st.tabs(["Ask", "Compare"])
    with ask_tab:
        render_ask_tab()
    with compare_tab:
        render_compare_tab()


main()
