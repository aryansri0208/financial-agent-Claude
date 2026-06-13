import json
import os
import subprocess
import sys
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(ROOT, "analysis_output.json")
STAGE1_DIR = os.path.join(ROOT, "data", "stage1")
STAGE2_DIR = os.path.join(ROOT, "data", "stage2")

st.set_page_config(page_title="Portfolio Advisor", layout="wide", page_icon="📈")

# ── Helpers ─────────────────────────────────────────────────────────────────

def load_output() -> dict:
    if not os.path.exists(OUTPUT_FILE):
        return {}
    with open(OUTPUT_FILE) as f:
        return json.load(f)


def load_stage(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def badge(rec: str) -> str:
    colors = {"HOLD": "🟡", "ADD": "🟢", "REDUCE": "🟠", "SELL": "🔴",
              "HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}
    return f"{colors.get(rec, '⚪')} {rec}"


def badge_emoji(rec: str) -> str:
    colors = {"HOLD": "🟡", "ADD": "🟢", "REDUCE": "🟠", "SELL": "🔴",
              "HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}
    return colors.get(rec.upper() if rec else "", "⚪")


def fmt_currency(val) -> str:
    if val is None:
        return "—"
    try:
        return f"${float(val):,.2f}"
    except Exception:
        return str(val)


def fmt_pct(val) -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val):+.2f}%"
    except Exception:
        return str(val)


# ── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.title("📈 Portfolio Advisor")
st.sidebar.markdown("---")

if st.sidebar.button("🔄 Run Full Analysis", use_container_width=True):
    with st.spinner("Running multi-agent pipeline… this takes 2-5 minutes."):
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "orchestrator.py")],
            capture_output=True, text=True, cwd=ROOT
        )
    if result.returncode == 0:
        st.sidebar.success("Analysis complete!")
        st.rerun()
    else:
        st.sidebar.error("Pipeline failed. Check terminal output.")
        st.sidebar.code(result.stderr[-2000:])

data = load_output()
technicals_data = load_stage(os.path.join(STAGE2_DIR, "technicals.json"))
_raw_news = load_stage(os.path.join(STAGE1_DIR, "news.json"))
# Flatten agent-generated "data" wrapper if present
if "data" in _raw_news and isinstance(_raw_news["data"], dict):
    news_data = _raw_news["data"]
    news_data.setdefault("sources", _raw_news.get("sources", []))
else:
    news_data = _raw_news
portfolio_raw = load_stage(os.path.join(STAGE1_DIR, "portfolio.json"))

if data:
    run_time = datetime.fromtimestamp(os.path.getmtime(OUTPUT_FILE)).strftime("%b %d %Y %H:%M")
    st.sidebar.caption(f"Last updated: {run_time}")
else:
    st.sidebar.warning("No analysis yet. Click 'Run Full Analysis' to start.")

# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_portfolio, tab_opportunities, tab_technicals, tab_news, tab_strategy, tab_sources = st.tabs([
    "💼 Portfolio", "🚀 Opportunities", "📊 Technicals", "📰 News & Sentiment",
    "🧠 Strategy", "🔗 Sources"
])

# ════════════════════════════════════════════════════════════════════════
# TAB 1: PORTFOLIO
# ════════════════════════════════════════════════════════════════════════
with tab_portfolio:
    st.header("Current Portfolio")

    if not data:
        st.info("Run the analysis pipeline to see your portfolio.")
    else:
        summary = data.get("portfolio_summary", {})
        col1, col2, col3 = st.columns(3)
        col1.metric("Portfolio Value", fmt_currency(summary.get("total_value")))
        col2.metric("Total P&L", fmt_currency(summary.get("total_pl")), fmt_pct(summary.get("total_pl_pct")))
        col3.metric("Health Score", f"{summary.get('health_score', '—')} / 10")

        if summary.get("assessment"):
            st.info(summary["assessment"])

        holds = data.get("holds", [])
        sells = data.get("sells", [])
        all_holdings_analysis = data.get("portfolio_summary", {})

        holdings_analysis = (
            load_stage(os.path.join(STAGE2_DIR, "portfolio_analysis.json"))
            .get("holdings_analysis", [])
        )

        if holdings_analysis:
            rows = []
            for h in holdings_analysis:
                ticker = h.get("ticker", "")
                raw_holding = next((x for x in portfolio_raw.get("holdings", []) if x["ticker"] == ticker), {})
                rows.append({
                    "Ticker": ticker,
                    "Shares": raw_holding.get("quantity", "—"),
                    "Avg Cost": fmt_currency(raw_holding.get("avg_cost")),
                    "Current": fmt_currency(raw_holding.get("current_price")),
                    "P&L": fmt_currency(raw_holding.get("unrealized_pl")),
                    "P&L %": fmt_pct(raw_holding.get("unrealized_pl_pct")),
                    "Recommendation": badge(h.get("recommendation", "")),
                    "Exit Target": fmt_currency(h.get("exit_price_target")),
                    "Reasoning": h.get("reasoning", ""),
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Sector allocation donut
        if portfolio_raw.get("holdings"):
            fundamentals = load_stage(os.path.join(STAGE1_DIR, "fundamentals.json"))
            sector_map = {}
            for h in portfolio_raw["holdings"]:
                t = h["ticker"]
                sector = fundamentals.get(t, {}).get("sector", "Unknown")
                sector_map[sector] = sector_map.get(sector, 0) + h.get("current_value", 0)
            if sector_map:
                fig = go.Figure(go.Pie(
                    labels=list(sector_map.keys()),
                    values=list(sector_map.values()),
                    hole=0.4,
                ))
                fig.update_layout(title="Portfolio Allocation by Sector", height=350)
                st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════
# TAB 2: OPPORTUNITIES
# ════════════════════════════════════════════════════════════════════════
with tab_opportunities:
    st.header("Investment Opportunities")

    if not data:
        st.info("Run the analysis pipeline to see opportunities.")
    else:
        new_buys = data.get("new_buys", [])
        if not new_buys:
            st.info("No new opportunities identified in this run.")
        else:
            stocks = [x for x in new_buys if x.get("type") == "stock"]
            etfs = [x for x in new_buys if x.get("type") == "etf"]
            cryptos = [x for x in new_buys if x.get("type") == "crypto"]

            if stocks:
                st.subheader("📈 Stocks")
                _stock_name_cache: dict = {}
                for s in stocks:
                    ticker = s.get("ticker", "")
                    conviction = s.get("conviction", "")
                    if ticker not in _stock_name_cache:
                        try:
                            _stock_name_cache[ticker] = yf.Ticker(ticker).info.get("longName", ticker)
                        except Exception:
                            _stock_name_cache[ticker] = ticker
                    full_name = _stock_name_cache[ticker]
                    header = f"{badge_emoji(conviction)}  {full_name} ({ticker})"
                    with st.expander(header):
                        try:
                            current_price = yf.Ticker(ticker).fast_info.last_price
                        except Exception:
                            current_price = None
                        c1, c2, c3, c4, c5 = st.columns(5)
                        c1.metric("Current Price", fmt_currency(current_price))
                        c2.metric("Entry Low", fmt_currency(s.get("entry_price_low")))
                        c3.metric("Entry High", fmt_currency(s.get("entry_price_high")))
                        c4.metric("12m Target", fmt_currency(s.get("price_target_12m")))
                        c5.metric("Best Time", s.get("best_time_to_buy", "—"))
                        alloc = s.get("suggested_allocation", s.get("suggested_allocation_pct", "—"))
                        if alloc != "—":
                            st.metric("Suggested Allocation", f"{alloc}%")
                        st.markdown("[🔗 News & Sentiment](#news-sentiment)")
                        st.markdown(f"**Reasoning:** {s.get('reasoning','')}")
                        if s.get("catalysts"):
                            st.markdown("**Catalysts:** " + " · ".join(s["catalysts"]))
                        if s.get("risks"):
                            st.markdown("**Risks:** " + " · ".join(s["risks"]))

            if etfs:
                st.subheader("🗂️ ETFs")
                for e in etfs:
                    etf_name = e.get("name") or ""
                    etf_ticker = e.get("ticker", "")
                    theme = e.get("theme", "")
                    name_part = f" — {etf_name}" if etf_name and etf_name != etf_ticker else ""
                    theme_part = f" ({theme})" if theme else ""
                    header = f"**{etf_ticker}**{name_part}{theme_part}"
                    with st.expander(header):
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Expense Ratio", f"{e.get('expense_ratio','—')}%")
                        c2.metric("1yr Return", fmt_pct(e.get("1y_return_pct")))
                        c3.metric("Suggested Alloc", f"{e.get('suggested_allocation_pct','—')}%")
                        st.markdown(f"**Reasoning:** {e.get('reasoning','')}")

            if cryptos:
                st.subheader("₿ Crypto")
                for c in cryptos:
                    with st.expander(f"{badge(c.get('risk_level',''))}  **{c.get('symbol','').upper()}** ({c.get('coin_id','')})"):
                        col1, col2 = st.columns(2)
                        col1.metric("Entry Price", fmt_currency(c.get("entry_price_usd")))
                        col2.metric("Risk", c.get("risk_level", "—"))
                        st.markdown(f"**Thesis:** {c.get('thesis','')}")

        watchlist = data.get("watchlist", [])
        if watchlist:
            st.subheader("👁️ Watchlist")
            for item in watchlist:
                if isinstance(item, dict):
                    st.markdown(f"- **{item.get('ticker',item)}** — {item.get('reason','Monitor')}")
                else:
                    st.markdown(f"- **{item}**")


# ════════════════════════════════════════════════════════════════════════
# TAB 3: TECHNICALS
# ════════════════════════════════════════════════════════════════════════
with tab_technicals:
    st.header("Technical Analysis")

    technicals = technicals_data.get("technicals", {})
    price_history = technicals_data.get("price_history", {})

    if not technicals:
        st.info("Run the analysis pipeline to see technical charts.")
    else:
        ticker_choice = st.selectbox("Select ticker", sorted(technicals.keys()))

        if ticker_choice:
            t = technicals[ticker_choice]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Price", fmt_currency(t.get("current_price")))
            c2.metric("RSI (14)", t.get("rsi", "—"), t.get("rsi_signal", ""))
            c3.metric("Trend", t.get("trend", "—"))
            c4.metric("MACD", "Bullish ↑" if t.get("macd_bullish") else "Bearish ↓")

            col_a, col_b = st.columns(2)
            col_a.metric("Support", fmt_currency(t.get("support")))
            col_a.metric("Entry Low", fmt_currency(t.get("entry_range_low")))
            col_b.metric("Resistance", fmt_currency(t.get("resistance")))
            col_b.metric("Entry High", fmt_currency(t.get("entry_range_high")))
            st.metric("Stop Loss", fmt_currency(t.get("stop_loss")))

            if t.get("technical_summary"):
                st.info(t["technical_summary"])

            # Price chart with SMA overlays
            hist = price_history.get(ticker_choice, [])
            if not hist:
                st.caption("📉 Price history chart unavailable — re-run analysis to collect 1-year OHLCV data.")
            if hist:
                df_hist = pd.DataFrame(hist)
                df_hist["date"] = pd.to_datetime(df_hist["date"])
                df_hist = df_hist.sort_values("date")
                df_hist["sma20"] = df_hist["close"].rolling(20).mean()
                df_hist["sma50"] = df_hist["close"].rolling(50).mean()
                df_hist["sma200"] = df_hist["close"].rolling(200).mean()

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_hist["date"], y=df_hist["close"], name="Price", line=dict(color="#00b4d8", width=2)))
                fig.add_trace(go.Scatter(x=df_hist["date"], y=df_hist["sma20"], name="SMA 20", line=dict(color="#f77f00", width=1, dash="dot")))
                fig.add_trace(go.Scatter(x=df_hist["date"], y=df_hist["sma50"], name="SMA 50", line=dict(color="#fcbf49", width=1, dash="dot")))
                fig.add_trace(go.Scatter(x=df_hist["date"], y=df_hist["sma200"], name="SMA 200", line=dict(color="#d62828", width=1, dash="dot")))
                fig.update_layout(title=f"{ticker_choice} — 1 Year Price + SMAs", height=420, template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)

            # SMA comparison bar
            sma_fig = go.Figure(go.Bar(
                x=["SMA 20", "SMA 50", "SMA 200", "Current"],
                y=[t.get("sma_20"), t.get("sma_50"), t.get("sma_200"), t.get("current_price")],
                marker_color=["#f77f00", "#fcbf49", "#d62828", "#00b4d8"],
            ))
            sma_fig.update_layout(title="Price vs Moving Averages", height=280, template="plotly_dark")
            st.plotly_chart(sma_fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════
# TAB 4: NEWS & SENTIMENT
# ════════════════════════════════════════════════════════════════════════
with tab_news:
    st.header("News & Sentiment")

    if not news_data:
        st.info("No news data yet — run the analysis pipeline to populate this tab.")
    else:
        tickers_with_news = [k for k in news_data.keys() if k != "sources"]
        selected_ticker = st.selectbox("Filter by ticker", ["All"] + sorted(tickers_with_news))

        feed_tickers = tickers_with_news if selected_ticker == "All" else [selected_ticker]

        SENTIMENT_COLORS = {
            "Bullish": "🟢", "Somewhat-Bullish": "🟢",
            "Bearish": "🔴", "Somewhat-Bearish": "🔴",
            "Neutral": "⚪",
        }

        for tk in feed_tickers:
            td = news_data.get(tk, {})
            bull = td.get("bullish_pct")
            bear = td.get("bearish_pct")
            score = td.get("sentiment_score")
            mentions = td.get("article_mentions_7d")
            has_sentiment = bull is not None and bear is not None

            # Determine sentiment source tag
            src_list = td.get("sources", [])
            src_names = [s.get("source_name", "") if isinstance(s, dict) else str(s) for s in src_list]
            if any("Alpha Vantage" in s for s in src_names):
                src_tag = "via Alpha Vantage"
            elif any("VADER" in s for s in src_names):
                src_tag = "via VADER (local)"
            elif any("Finnhub" in s for s in src_names):
                src_tag = "articles only (Finnhub)"
            else:
                src_tag = ""

            if has_sentiment:
                net = round(bull - bear, 2)
                sentiment_icon = "🟢" if net > 5 else "🔴" if net < -5 else "⚪"
                header = f"{tk} {sentiment_icon} Sentiment: {net:+.1f}pp"
                st.subheader(header)
                c1, c2, c3 = st.columns(3)
                c1.metric("Bullish", fmt_pct(bull))
                c2.metric("Bearish", fmt_pct(bear))
                c3.metric("Raw Score", f"{score:+.3f}" if score is not None else "—")
                if mentions:
                    st.caption(f"📰 {mentions} articles indexed · {src_tag}")
                elif src_tag:
                    st.caption(f"Sentiment source: {src_tag}")
            else:
                st.subheader(f"{tk} — News")
                st.caption("Sentiment scores unavailable for this ticker")

            articles = td.get("articles", [])
            for article in articles:
                if not article.get("headline"):
                    continue
                url = article.get("url", "")
                headline = article["headline"]
                source = article.get("source", "")
                label = article.get("sentiment_label", "")
                label_icon = SENTIMENT_COLORS.get(label, "")
                dt_raw = article.get("datetime", "")
                # Handle both unix timestamp and AV string format (e.g. "20260608T143000")
                date_str = ""
                if dt_raw:
                    try:
                        date_str = datetime.fromtimestamp(int(dt_raw)).strftime("%b %d")
                    except (ValueError, TypeError):
                        try:
                            date_str = datetime.strptime(str(dt_raw)[:8], "%Y%m%d").strftime("%b %d")
                        except Exception:
                            date_str = ""
                link = f"[{headline}]({url})" if url else headline
                label_str = f" {label_icon} `{label}`" if label else ""
                date_str_fmt = f" · {date_str}" if date_str else ""
                st.markdown(f"- {link}  \n  `{source}`{date_str_fmt}{label_str}")

            st.markdown("---")


# ════════════════════════════════════════════════════════════════════════
# TAB 5: STRATEGY
# ════════════════════════════════════════════════════════════════════════
with tab_strategy:
    st.header("Overall Strategy")

    if not data:
        st.info("Run the analysis pipeline to see the strategy.")
    else:
        macro = data.get("macro_context", "")
        if macro:
            st.subheader("🌍 Macro Context")
            st.write(macro)

        strategy = data.get("strategy_summary", "")
        if strategy:
            st.subheader("🧠 Strategy Summary")
            st.write(strategy)

        portfolio_anal = load_stage(os.path.join(STAGE2_DIR, "portfolio_analysis.json"))
        risks = portfolio_anal.get("sector_concentration_risks", [])
        if risks:
            st.subheader("⚠️ Concentration Risks")
            for r in risks:
                readable = r.replace("_", " ").replace("-", " ") if isinstance(r, str) else r
                st.warning(readable)

        rebal = portfolio_anal.get("rebalancing_suggestions", [])
        if rebal:
            st.subheader("⚖️ Rebalancing Suggestions")
            for r in rebal:
                readable = r.replace("_", " ").replace("-", " ") if isinstance(r, str) else r
                st.markdown(f"- {readable}")

        st.subheader("📥 Download Full Report")
        st.download_button(
            label="Download analysis_output.json",
            data=json.dumps(data, indent=2),
            file_name=f"portfolio_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )


# ════════════════════════════════════════════════════════════════════════
# TAB 6: SOURCES
# ════════════════════════════════════════════════════════════════════════
with tab_sources:
    st.header("Data Sources Used in This Analysis")
    st.caption("Every data point powering the recommendations above — trace any conclusion back to its raw source.")

    if not data:
        st.info("Run the analysis pipeline to see sources.")
    else:
        sources_by_category = data.get("sources", {})

        if isinstance(sources_by_category, list):
            # Flat list fallback — group by source_name
            grouped: dict[str, list] = {}
            for s in sources_by_category:
                if isinstance(s, str):
                    grouped.setdefault("other", []).append(s)
                else:
                    cat = s.get("data_type", "other").split("_")[0]
                    grouped.setdefault(cat, []).append(s)
            sources_by_category = grouped

        category_icons = {
            "market_data": "📊 Market Data",
            "macro": "🏦 Macro / FRED",
            "crypto": "₿ Crypto",
            "news": "📰 News & Sentiment",
            "filings": "📋 SEC Filings",
        }

        if not sources_by_category:
            st.info("No source metadata available in this analysis run.")
        else:
            for cat_key, cat_label in category_icons.items():
                sources = sources_by_category.get(cat_key, [])
                if not sources:
                    continue
                st.subheader(cat_label)
                rows = []
                seen = set()
                for s in sources:
                    if isinstance(s, str):
                        if s not in seen:
                            seen.add(s)
                            rows.append({"Source": s, "Data Type": "—", "Agent": "—", "Fetched At": "—"})
                        continue
                    key = (s.get("source_name"), s.get("data_type"))
                    if key in seen:
                        continue
                    seen.add(key)
                    url = s.get("url", "")
                    link = f"[{s.get('source_name','')}]({url})" if url else s.get("source_name", "")
                    rows.append({
                        "Source": link,
                        "Data Type": s.get("data_type", ""),
                        "Agent": s.get("agent", "—"),
                        "Fetched At": s.get("timestamp", "—"),
                    })
                if rows:
                    df = pd.DataFrame(rows)
                    st.markdown(df.to_markdown(index=False), unsafe_allow_html=True)
                    st.markdown("")

            # Also expose any uncategorized sources
            all_known = set(category_icons.keys())
            other = {k: v for k, v in sources_by_category.items() if k not in all_known}
            if other:
                st.subheader("📎 Other Sources")
                for cat, src_list in other.items():
                    for s in src_list:
                        if isinstance(s, str):
                            st.markdown(f"- {s}")
                            continue
                        url = s.get("url", "")
                        name = s.get("source_name", "")
                        st.markdown(f"- [{name}]({url}) — {s.get('data_type','')}")
