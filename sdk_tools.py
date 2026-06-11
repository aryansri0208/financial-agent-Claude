"""
In-process SDK MCP server wrapping all finance tools from mcp_server.py.

Usage in agents:
    from sdk_tools import finance_mcp_server
    options = ClaudeAgentOptions(mcp_servers={"finance": finance_mcp_server}, ...)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from claude_agent_sdk import tool, create_sdk_mcp_server

# Import the raw implementation functions from mcp_server
from mcp_server import (
    _get_portfolio,
    _get_stock_fundamentals,
    _get_analyst_targets,
    _get_insider_trades,
    _get_institutional_holdings,
    _get_macro_data,
    _get_sector_performance,
    _get_crypto_data,
    _get_crypto_trending,
    _get_etf_info,
    _get_news_and_sentiment,
    _get_technical_indicators,
    _get_price_history,
)


def _wrap(result: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


@tool("get_portfolio", "Fetch Robinhood portfolio: holdings, quantities, avg cost, current value", {})
async def get_portfolio(args):
    return _wrap(await _get_portfolio())


@tool("get_stock_fundamentals", "Get P/E, EPS, market cap, beta, revenue growth for a ticker", {"ticker": str})
async def get_stock_fundamentals(args):
    return _wrap(await _get_stock_fundamentals(args["ticker"]))


@tool("get_analyst_targets", "Get analyst consensus rating and price target range for a ticker", {"ticker": str})
async def get_analyst_targets(args):
    return _wrap(await _get_analyst_targets(args["ticker"]))


@tool("get_insider_trades", "Get recent insider buy/sell activity (Form 4) for a ticker", {"ticker": str})
async def get_insider_trades(args):
    return _wrap(await _get_insider_trades(args["ticker"]))


@tool("get_institutional_holdings", "Get top institutional/hedge fund holders (13F filings) for a ticker", {"ticker": str})
async def get_institutional_holdings(args):
    return _wrap(await _get_institutional_holdings(args["ticker"]))


@tool("get_macro_data", "Get Fed funds rate, CPI, unemployment, yield curve from FRED", {})
async def get_macro_data(args):
    return _wrap(await _get_macro_data())


@tool("get_sector_performance", "Get sector ETF 1-month and YTD performance", {})
async def get_sector_performance(args):
    return _wrap(await _get_sector_performance())


@tool("get_crypto_data", "Get price, market cap, 7d/30d change for a cryptocurrency", {"coin_id": str})
async def get_crypto_data(args):
    return _wrap(await _get_crypto_data(args["coin_id"]))


@tool("get_crypto_trending", "Get top 7 trending coins on CoinGecko right now", {})
async def get_crypto_trending(args):
    return _wrap(await _get_crypto_trending())


@tool("get_etf_info", "Get ETF expense ratio, top holdings, and 1yr/3yr performance", {"ticker": str})
async def get_etf_info(args):
    return _wrap(await _get_etf_info(args["ticker"]))


@tool("get_news_and_sentiment", "Get latest news and Reddit/social sentiment score for a ticker", {"ticker": str})
async def get_news_and_sentiment(args):
    return _wrap(await _get_news_and_sentiment(args["ticker"]))


@tool("get_technical_indicators", "Get SMA20/50/200, RSI, MACD for a ticker", {"ticker": str})
async def get_technical_indicators(args):
    return _wrap(await _get_technical_indicators(args["ticker"]))


@tool("get_price_history", "Get 1-year daily OHLCV price history for a ticker", {"ticker": str})
async def get_price_history(args):
    return _wrap(await _get_price_history(args["ticker"]))


finance_mcp_server = create_sdk_mcp_server(
    name="finance",
    version="1.0.0",
    tools=[
        get_portfolio,
        get_stock_fundamentals,
        get_analyst_targets,
        get_insider_trades,
        get_institutional_holdings,
        get_macro_data,
        get_sector_performance,
        get_crypto_data,
        get_crypto_trending,
        get_etf_info,
        get_news_and_sentiment,
        get_technical_indicators,
        get_price_history,
    ],
)
