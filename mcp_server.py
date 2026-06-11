import os
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import mcp.server.stdio
from mcp.server import Server
from mcp.types import Tool, TextContent

# Alpha Vantage free tier: 5 requests/minute — track last call time
_av_last_call: float = 0.0
_AV_MIN_INTERVAL = 13.0  # seconds between AV requests (60/5 + 1s buffer)

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
ROBINHOOD_USERNAME = os.getenv("ROBINHOOD_USERNAME", "")
ROBINHOOD_PASSWORD = os.getenv("ROBINHOOD_PASSWORD", "")

server = Server("finance-tools")


def _source(name: str, url: str, data_type: str) -> dict:
    return {"source_name": name, "url": url, "data_type": data_type, "timestamp": datetime.utcnow().isoformat()}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="get_portfolio", description="Fetch Robinhood portfolio: holdings, quantities, avg cost, current value", inputSchema={"type": "object", "properties": {}, "required": []}),
        Tool(name="get_stock_fundamentals", description="Get P/E, EPS, market cap, beta, revenue growth for a ticker", inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
        Tool(name="get_analyst_targets", description="Get analyst consensus rating and price target range for a ticker", inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
        Tool(name="get_insider_trades", description="Get recent insider buy/sell activity (Form 4) for a ticker", inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
        Tool(name="get_institutional_holdings", description="Get top institutional/hedge fund holders (13F filings) for a ticker", inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
        Tool(name="get_macro_data", description="Get Fed funds rate, CPI, unemployment, yield curve from FRED", inputSchema={"type": "object", "properties": {}, "required": []}),
        Tool(name="get_sector_performance", description="Get sector ETF 1-month and YTD performance", inputSchema={"type": "object", "properties": {}, "required": []}),
        Tool(name="get_crypto_data", description="Get price, market cap, 7d/30d change for a cryptocurrency", inputSchema={"type": "object", "properties": {"coin_id": {"type": "string", "description": "CoinGecko coin id, e.g. bitcoin, ethereum, solana"}}, "required": ["coin_id"]}),
        Tool(name="get_crypto_trending", description="Get top 7 trending coins on CoinGecko right now", inputSchema={"type": "object", "properties": {}, "required": []}),
        Tool(name="get_etf_info", description="Get ETF expense ratio, top holdings, and 1yr/3yr performance", inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
        Tool(name="get_news_and_sentiment", description="Get latest news and Reddit/social sentiment score for a ticker", inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
        Tool(name="get_technical_indicators", description="Get SMA20/50/200, RSI, MACD for a ticker", inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
        Tool(name="get_price_history", description="Get 1-year daily OHLCV price history for a ticker", inputSchema={"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
    except Exception as e:
        result = {"error": str(e), "tool": name}
    return [TextContent(type="text", text=json.dumps(result, default=str))]


async def _dispatch(name: str, args: dict) -> dict:
    if name == "get_portfolio":
        return await _get_portfolio()
    elif name == "get_stock_fundamentals":
        return await _get_stock_fundamentals(args["ticker"])
    elif name == "get_analyst_targets":
        return await _get_analyst_targets(args["ticker"])
    elif name == "get_insider_trades":
        return await _get_insider_trades(args["ticker"])
    elif name == "get_institutional_holdings":
        return await _get_institutional_holdings(args["ticker"])
    elif name == "get_macro_data":
        return await _get_macro_data()
    elif name == "get_sector_performance":
        return await _get_sector_performance()
    elif name == "get_crypto_data":
        return await _get_crypto_data(args["coin_id"])
    elif name == "get_crypto_trending":
        return await _get_crypto_trending()
    elif name == "get_etf_info":
        return await _get_etf_info(args["ticker"])
    elif name == "get_news_and_sentiment":
        return await _get_news_and_sentiment(args["ticker"])
    elif name == "get_technical_indicators":
        return await _get_technical_indicators(args["ticker"])
    elif name == "get_price_history":
        return await _get_price_history(args["ticker"])
    raise ValueError(f"Unknown tool: {name}")


# ── Tool implementations ────────────────────────────────────────────────────

async def _get_portfolio() -> dict:
    import robin_stocks.robinhood as rh
    rh.login(ROBINHOOD_USERNAME, ROBINHOOD_PASSWORD, store_session=True)
    positions = rh.get_open_stock_positions()
    holdings = []
    for p in positions:
        try:
            qty = float(p.get("quantity") or 0)
            if qty == 0:
                continue  # skip closed/zero-quantity positions
            instrument = rh.get_instrument_by_url(p["instrument"])
            if not instrument:
                continue
            ticker = instrument.get("symbol", "")
            if not ticker:
                continue
            avg_cost = float(p.get("average_buy_price") or 0)
            quotes = rh.get_latest_price(ticker)
            current_price = float(quotes[0]) if quotes and quotes[0] else avg_cost
            holdings.append({
                "ticker": ticker,
                "quantity": qty,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "current_value": round(qty * current_price, 2),
                "unrealized_pl": round(qty * (current_price - avg_cost), 2),
                "unrealized_pl_pct": round((current_price - avg_cost) / avg_cost * 100, 2) if avg_cost else 0,
            })
        except Exception as e:
            # Skip any individual position that fails — don't abort the whole portfolio fetch
            continue
    return {
        "holdings": holdings,
        "sources": [_source("Robinhood", "https://robinhood.com", "portfolio_holdings")],
    }


async def _get_stock_fundamentals(ticker: str) -> dict:
    import finnhub
    import yfinance as yf
    fc = finnhub.Client(api_key=FINNHUB_API_KEY)
    basic = fc.company_basic_financials(ticker, "all")
    profile = fc.company_profile2(symbol=ticker)
    yf_ticker = yf.Ticker(ticker)
    info = yf_ticker.info
    metrics = basic.get("metric", {})
    return {
        "ticker": ticker,
        "name": profile.get("name", ""),
        "sector": profile.get("finnhubIndustry", info.get("sector", "")),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE") or metrics.get("peBasicExclExtraTTM"),
        "forward_pe": info.get("forwardPE"),
        "eps_ttm": info.get("trailingEps") or metrics.get("epsBasicExclExtraItemsTTM"),
        "revenue_growth_yoy": metrics.get("revenueGrowth3Y"),
        "profit_margin": info.get("profitMargins"),
        "beta": info.get("beta") or metrics.get("beta"),
        "dividend_yield": info.get("dividendYield"),
        "52w_high": metrics.get("52WeekHigh"),
        "52w_low": metrics.get("52WeekLow"),
        "debt_to_equity": info.get("debtToEquity"),
        "roe": metrics.get("roeRfy"),
        "sources": [
            _source("Finnhub", f"https://finnhub.io/api/v1/stock/metric?symbol={ticker}", "fundamentals"),
            _source("Yahoo Finance", f"https://finance.yahoo.com/quote/{ticker}", "fundamentals"),
        ],
    }


async def _get_analyst_targets(ticker: str) -> dict:
    import finnhub
    fc = finnhub.Client(api_key=FINNHUB_API_KEY)
    rec = fc.recommendation_trends(ticker)
    target = fc.price_target(ticker)
    latest_rec = rec[0] if rec else {}
    return {
        "ticker": ticker,
        "strong_buy": latest_rec.get("strongBuy", 0),
        "buy": latest_rec.get("buy", 0),
        "hold": latest_rec.get("hold", 0),
        "sell": latest_rec.get("sell", 0),
        "strong_sell": latest_rec.get("strongSell", 0),
        "target_high": target.get("targetHigh"),
        "target_low": target.get("targetLow"),
        "target_mean": target.get("targetMean"),
        "target_median": target.get("targetMedian"),
        "sources": [_source("Finnhub", f"https://finnhub.io/api/v1/stock/recommendation?symbol={ticker}", "analyst_ratings")],
    }


async def _get_insider_trades(ticker: str) -> dict:
    import finnhub
    fc = finnhub.Client(api_key=FINNHUB_API_KEY)
    three_months_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    data = fc.stock_insider_transactions(ticker, three_months_ago, today)
    trades = []
    for t in (data.get("data") or [])[:20]:
        trades.append({
            "name": t.get("name"),
            "share": t.get("share"),
            "transaction_price": t.get("transactionPrice"),
            "transaction_date": t.get("transactionDate"),
            "transaction_code": t.get("transactionCode"),
        })
    return {
        "ticker": ticker,
        "trades": trades,
        "sources": [_source("Finnhub", f"https://finnhub.io/api/v1/stock/insider-transactions?symbol={ticker}", "insider_trading")],
    }


async def _get_institutional_holdings(ticker: str) -> dict:
    import finnhub
    fc = finnhub.Client(api_key=FINNHUB_API_KEY)
    data = fc.ownership(ticker, limit=10)
    holders = []
    for h in (data.get("ownership") or []):
        holders.append({
            "name": h.get("name"),
            "shares": h.get("share"),
            "change": h.get("change"),
            "pct_of_shares_outstanding": h.get("currentHolding"),
        })
    return {
        "ticker": ticker,
        "top_institutional_holders": holders,
        "sources": [_source("Finnhub", f"https://finnhub.io/api/v1/stock/ownership?symbol={ticker}", "institutional_holdings")],
    }


async def _get_macro_data() -> dict:
    from fredapi import Fred
    fred = Fred(api_key=FRED_API_KEY)

    def _latest(series_id: str):
        try:
            s = fred.get_series(series_id)
            return round(float(s.dropna().iloc[-1]), 4)
        except Exception:
            return None

    fed_rate = _latest("FEDFUNDS")
    cpi_yoy = _latest("CPIAUCSL")
    unemployment = _latest("UNRATE")
    t10y = _latest("GS10")
    t2y = _latest("GS2")
    yield_spread = round(t10y - t2y, 4) if t10y and t2y else None

    return {
        "fed_funds_rate": fed_rate,
        "cpi_latest": cpi_yoy,
        "unemployment_rate": unemployment,
        "10y_treasury_yield": t10y,
        "2y_treasury_yield": t2y,
        "yield_curve_spread_10y_2y": yield_spread,
        "yield_curve_inverted": yield_spread < 0 if yield_spread is not None else None,
        "sources": [
            _source("FRED", "https://fred.stlouisfed.org/series/FEDFUNDS", "macro_fed_rate"),
            _source("FRED", "https://fred.stlouisfed.org/series/CPIAUCSL", "macro_cpi"),
            _source("FRED", "https://fred.stlouisfed.org/series/UNRATE", "macro_unemployment"),
            _source("FRED", "https://fred.stlouisfed.org/series/GS10", "macro_yield_curve"),
        ],
    }


async def _get_sector_performance() -> dict:
    import yfinance as yf
    sector_etfs = {
        "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
        "Energy": "XLE", "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
        "Industrials": "XLI", "Materials": "XLB", "Utilities": "XLU",
        "Real Estate": "XLRE", "Communication Services": "XLC",
    }
    results = []
    for sector, etf in sector_etfs.items():
        try:
            t = yf.Ticker(etf)
            hist = t.history(period="1mo")
            ytd_hist = t.history(period="ytd")
            one_month = round((hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100, 2) if len(hist) > 1 else None
            ytd = round((ytd_hist["Close"].iloc[-1] / ytd_hist["Close"].iloc[0] - 1) * 100, 2) if len(ytd_hist) > 1 else None
            results.append({"sector": sector, "etf": etf, "1m_return_pct": one_month, "ytd_return_pct": ytd})
        except Exception:
            results.append({"sector": sector, "etf": etf, "1m_return_pct": None, "ytd_return_pct": None})
    return {
        "sectors": results,
        "sources": [_source("Yahoo Finance", "https://finance.yahoo.com", "sector_etf_performance")],
    }


async def _get_crypto_data(coin_id: str) -> dict:
    from pycoingecko import CoinGeckoAPI
    cg = CoinGeckoAPI()
    data = cg.get_coin_by_id(
        coin_id,
        localization=False,
        tickers=False,
        market_data=True,
        community_data=False,
        developer_data=False,
    )
    md = data.get("market_data", {})
    return {
        "coin_id": coin_id,
        "name": data.get("name"),
        "symbol": data.get("symbol", "").upper(),
        "current_price_usd": md.get("current_price", {}).get("usd"),
        "market_cap_usd": md.get("market_cap", {}).get("usd"),
        "market_cap_rank": data.get("market_cap_rank"),
        "24h_change_pct": md.get("price_change_percentage_24h"),
        "7d_change_pct": md.get("price_change_percentage_7d"),
        "30d_change_pct": md.get("price_change_percentage_30d"),
        "ath": md.get("ath", {}).get("usd"),
        "ath_change_pct": md.get("ath_change_percentage", {}).get("usd"),
        "total_volume_usd": md.get("total_volume", {}).get("usd"),
        "circulating_supply": md.get("circulating_supply"),
        "max_supply": md.get("max_supply"),
        "sources": [_source("CoinGecko", f"https://www.coingecko.com/en/coins/{coin_id}", "crypto_market_data")],
    }


async def _get_crypto_trending() -> dict:
    from pycoingecko import CoinGeckoAPI
    cg = CoinGeckoAPI()
    data = cg.get_search_trending()
    coins = []
    for item in data.get("coins", []):
        c = item.get("item", {})
        coins.append({
            "name": c.get("name"),
            "symbol": c.get("symbol"),
            "market_cap_rank": c.get("market_cap_rank"),
            "coin_id": c.get("id"),
        })
    return {
        "trending_coins": coins,
        "sources": [_source("CoinGecko", "https://www.coingecko.com/en/search/trending", "crypto_trending")],
    }


async def _get_etf_info(ticker: str) -> dict:
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = t.info
    hist_1y = t.history(period="1y")
    hist_3y = t.history(period="3y")
    ret_1y = round((hist_1y["Close"].iloc[-1] / hist_1y["Close"].iloc[0] - 1) * 100, 2) if len(hist_1y) > 1 else None
    ret_3y = round((hist_3y["Close"].iloc[-1] / hist_3y["Close"].iloc[0] - 1) * 100, 2) if len(hist_3y) > 1 else None
    holdings = []
    try:
        hdf = t.funds_data.top_holdings if hasattr(t, "funds_data") else None
        if hdf is not None:
            for _, row in hdf.head(10).iterrows():
                holdings.append({"symbol": row.name, "holding_pct": round(float(row.get("holdingPercent", 0)) * 100, 2)})
    except Exception:
        pass
    return {
        "ticker": ticker,
        "name": info.get("longName", info.get("shortName", "")),
        "category": info.get("category", ""),
        "expense_ratio": info.get("annualReportExpenseRatio"),
        "nav": info.get("navPrice"),
        "total_assets": info.get("totalAssets"),
        "1y_return_pct": ret_1y,
        "3y_return_pct": ret_3y,
        "top_holdings": holdings,
        "sources": [_source("Yahoo Finance", f"https://finance.yahoo.com/quote/{ticker}", "etf_data")],
    }


async def _get_news_and_sentiment(ticker: str) -> dict:
    import requests as _req
    import finnhub

    articles = []
    bullish_pct = None
    bearish_pct = None
    sentiment_score = None
    article_mentions = None
    sources_used = []

    # ── Alpha Vantage NEWS_SENTIMENT (free, includes sentiment scores) ──────
    global _av_last_call
    av_ok = False
    if ALPHA_VANTAGE_API_KEY:
        # Enforce rate limit: max 5 requests/minute on free tier
        elapsed = time.monotonic() - _av_last_call
        if elapsed < _AV_MIN_INTERVAL:
            time.sleep(_AV_MIN_INTERVAL - elapsed)
        try:
            url = (
                "https://www.alphavantage.co/query"
                f"?function=NEWS_SENTIMENT&tickers={ticker}&limit=20&apikey={ALPHA_VANTAGE_API_KEY}"
            )
            resp = _req.get(url, timeout=15)
            _av_last_call = time.monotonic()
            av_data = resp.json()
            feed = av_data.get("feed", [])
            if feed:
                scores = []
                for art in feed:
                    for ts in art.get("ticker_sentiment", []):
                        if ts.get("ticker") == ticker:
                            scores.append(float(ts["ticker_sentiment_score"]))
                    articles.append({
                        "headline": art.get("title", ""),
                        "source": art.get("source", ""),
                        "url": art.get("url", ""),
                        "datetime": art.get("time_published", ""),
                        "sentiment_label": art.get("overall_sentiment_label", ""),
                    })
                if scores:
                    avg = sum(scores) / len(scores)
                    sentiment_score = round(avg, 4)
                    # Map score (-1..+1) to bullish/bearish percentages
                    bullish_pct = round((avg + 1) / 2 * 100, 2)
                    bearish_pct = round(100 - bullish_pct, 2)
                article_mentions = len(feed)
                sources_used.append(_source(
                    "Alpha Vantage",
                    f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}",
                    "news_sentiment",
                ))
                av_ok = True
        except Exception:
            pass

    # ── Finnhub company_news fallback (articles only) ───────────────────────
    if not av_ok:
        try:
            fc = finnhub.Client(api_key=FINNHUB_API_KEY)
            today = datetime.now().strftime("%Y-%m-%d")
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            news = fc.company_news(ticker, _from=week_ago, to=today)[:10]
            articles = [
                {"headline": n.get("headline"), "source": n.get("source"),
                 "url": n.get("url"), "datetime": str(n.get("datetime", ""))}
                for n in news
            ]
            article_mentions = len(articles)
            sources_used.append(_source(
                "Finnhub", f"https://finnhub.io/api/v1/company-news?symbol={ticker}", "news"
            ))
        except Exception:
            pass

    # ── VADER local sentiment fallback (free, no quota) ─────────────────────
    # Used when Alpha Vantage quota is exhausted or ticker has no AV coverage.
    if sentiment_score is None and articles:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            sia = SentimentIntensityAnalyzer()
            scores = [sia.polarity_scores(a["headline"])["compound"]
                      for a in articles if a.get("headline")]
            if scores:
                avg = sum(scores) / len(scores)
                sentiment_score = round(avg, 4)
                bullish_pct = round((avg + 1) / 2 * 100, 2)
                bearish_pct = round(100 - bullish_pct, 2)
                # Tag each article with its VADER label
                for a in articles:
                    if a.get("headline"):
                        s = sia.polarity_scores(a["headline"])["compound"]
                        a["sentiment_label"] = (
                            "Bullish" if s >= 0.05 else
                            "Bearish" if s <= -0.05 else "Neutral"
                        )
                sources_used.append(_source("VADER (local)", "https://github.com/cjhutto/vaderSentiment", "sentiment_vader"))
        except Exception:
            pass

    return {
        "ticker": ticker,
        "articles": articles[:10],
        "sentiment_score": sentiment_score,
        "bullish_pct": bullish_pct,
        "bearish_pct": bearish_pct,
        "article_mentions_7d": article_mentions,
        "sources": sources_used,
    }


async def _get_technical_indicators(ticker: str) -> dict:
    import pandas as pd
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period="1y")
    if hist.empty:
        return {"ticker": ticker, "error": "no data", "sources": []}
    close = hist["Close"]

    sma20 = round(float(close.rolling(20).mean().iloc[-1]), 4)
    sma50 = round(float(close.rolling(50).mean().iloc[-1]), 4)
    sma200 = round(float(close.rolling(200).mean().iloc[-1]), 4)
    current = round(float(close.iloc[-1]), 4)

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss
    rsi = round(float(100 - (100 / (1 + rs.iloc[-1]))), 2)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_val = round(float(macd_line.iloc[-1]), 4)
    signal_val = round(float(signal_line.iloc[-1]), 4)
    histogram = round(macd_val - signal_val, 4)

    return {
        "ticker": ticker,
        "current_price": current,
        "sma_20": sma20,
        "sma_50": sma50,
        "sma_200": sma200,
        "above_sma20": current > sma20,
        "above_sma50": current > sma50,
        "above_sma200": current > sma200,
        "rsi_14": rsi,
        "rsi_signal": "overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral",
        "macd": macd_val,
        "macd_signal": signal_val,
        "macd_histogram": histogram,
        "macd_bullish_cross": histogram > 0,
        "sources": [_source("Yahoo Finance (computed)", f"https://finance.yahoo.com/quote/{ticker}", "technical_indicators")],
    }


async def _get_price_history(ticker: str) -> dict:
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period="1y")
    records = []
    for ts, row in hist.iterrows():
        records.append({
            "date": ts.strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]),
        })
    return {
        "ticker": ticker,
        "history": records,
        "sources": [_source("Yahoo Finance", f"https://finance.yahoo.com/quote/{ticker}/history", "price_history")],
    }


if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server

    async def _main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_main())
