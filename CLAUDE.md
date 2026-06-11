# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Setup

```bash
source .venv/bin/activate
```

Required environment variables in `.env`:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (used by Stage 2 and Stage 3 agents) |
| `ROBINHOOD_USERNAME` | Robinhood account username |
| `ROBINHOOD_PASSWORD` | Robinhood account password |
| `FINNHUB_API_KEY` | Finnhub API key |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage API key |
| `FRED_API_KEY` | FRED (St. Louis Fed) API key |

## Running the Pipeline

Full pipeline (Stage 1 + 2 + 3):

```bash
python orchestrator.py
```

Skip Stage 1 and resume from Stage 2 (requires existing `data/stage1/*.json` files):

```bash
python orchestrator.py --resume
```

Full pipeline then launch dashboard:

```bash
python run.py
```

Dashboard only (skip pipeline):

```bash
python run.py --dashboard-only
```

Dashboard standalone:

```bash
streamlit run dashboard.py
```

## Architecture

The pipeline runs 10 agents across 3 stages. Progress is displayed via Rich in the terminal and written to `pipeline.log`.

### Stage 1 — Data Collection (6 agents, cost = $0)

All Stage 1 agents call Python functions from `mcp_server.py` directly. No Anthropic API calls are made. Each agent writes one JSON file to `data/stage1/`.

| Agent | Output file | External APIs |
|---|---|---|
| `stage1_portfolio` | `portfolio.json` | Robinhood (holdings, quantities, avg cost, current prices) |
| `stage1_fundamentals` | `fundamentals.json` | Finnhub (company profile, P/E, EPS, beta, revenue growth, ROE, 52-week high/low), Yahoo Finance (market cap, forward P/E, profit margin, dividend yield, debt-to-equity) |
| `stage1_macro` | `macro.json` | FRED (fed funds rate, CPI, unemployment, yield curve), Yahoo Finance (sector ETF 1m/YTD performance) |
| `stage1_crypto` | `crypto.json` | CoinGecko (price, market cap, 7d/30d returns for 8 major coins + trending list) |
| `stage1_news` | `news.json` | Alpha Vantage NEWS_SENTIMENT (primary), Finnhub company news (fallback), VADER local sentiment (fallback when no AV score) |
| `stage1_etf` | `etf.json` | Yahoo Finance (expense ratio, top holdings, 1yr/3yr returns for 12 watchlist ETFs) |

### Stage 2 — Analysis (3 agents, uses Anthropic API)

All Stage 2 agents use `anthropic.Anthropic().messages.create()` directly — not the Claude Agent SDK. Data is pre-loaded and formatted in Python; Claude only returns structured JSON. Model: `claude-haiku-4-5-20251001`.

| Agent | Output file | What it produces |
|---|---|---|
| `stage2_portfolio_analysis` | `portfolio_analysis.json` | Per-ticker HOLD/ADD/REDUCE/SELL recommendations with reasoning, exit/entry targets, risk flags, portfolio health score (1-10), sector concentration risks, rebalancing suggestions |
| `stage2_opportunities` | `opportunities.json` | New stock picks (3-5) with entry range and 12-month targets, ETF picks (2-3), crypto picks (2-3), and a watchlist — all excluding currently held tickers |
| `stage2_technicals` | `technicals.json` | Per-ticker trend (UPTREND/DOWNTREND/SIDEWAYS), RSI signal, MACD direction, support/resistance levels, entry range, stop loss, and technical summary. Pre-fetches raw indicator data via `_get_technical_indicators` then sends it to Claude for reasoning. |

### Stage 3 — Synthesis (1 agent, uses Anthropic API)

| Agent | Output file | What it produces |
|---|---|---|
| `stage3_synthesis` | `analysis_output.json` | Unified investment report: portfolio summary (value, P&L, health score), hold/sell action items, new buys with conviction levels, macro context narrative, strategy summary, and categorized source metadata |

## Key Files

| File | Purpose |
|---|---|
| `orchestrator.py` | Main async pipeline runner. Orchestrates all 10 agents sequentially, manages retries on rate-limit errors (up to 5 attempts, exponential backoff starting at 65s), displays Rich progress bar, writes `pipeline.log`. |
| `run.py` | Thin wrapper: runs `orchestrator.py` then launches the Streamlit dashboard. Supports `--dashboard-only` to skip the pipeline. |
| `mcp_server.py` | Houses all 13 data-fetching implementations (`_get_portfolio`, `_get_stock_fundamentals`, etc.). All Stage 1 agents import and call these functions directly; `stage2_technicals` also imports `_get_technical_indicators` to pre-fetch data before its Claude call. Also exposes the same functions as a proper MCP server over stdio when run as `__main__`. |
| `sdk_tools.py` | Wraps the same `mcp_server.py` functions as a `claude_agent_sdk` in-process MCP server (`finance_mcp_server`). Used when the Claude Agent SDK agentic loop is needed instead of direct API calls. |
| `dashboard.py` | Streamlit app with 6 tabs: Portfolio, Opportunities, Technicals, News & Sentiment, Strategy, Sources. Reads `analysis_output.json`, `data/stage1/news.json`, `data/stage1/portfolio.json`, `data/stage2/portfolio_analysis.json`, and `data/stage2/technicals.json`. Sidebar button triggers `orchestrator.py` directly. |
| `login_robinhood.py` | One-time Robinhood session setup. Logs in and caches a session token to `~/.tokens/robinhood.pickle`. Run this before the first pipeline execution on a new machine if Robinhood 2FA is required. |

## Data Flow

```
Stage 1 agents  ->  data/stage1/{portfolio,fundamentals,macro,crypto,news,etf}.json
Stage 2 agents  ->  data/stage2/{portfolio_analysis,opportunities,technicals}.json
Stage 3 agent   ->  analysis_output.json
```

`--resume` skips Stage 1 and reads existing `data/stage1/*.json` files. Useful when Stage 1 completed successfully and only Stage 2/3 need to re-run (e.g., after an Anthropic rate-limit failure).

## Dashboard

```bash
streamlit run dashboard.py
```

Reads from `analysis_output.json` for the main report, plus raw files from `data/stage1/` and `data/stage2/` for the Technicals and News tabs. The Technicals tab displays indicator values (trend, RSI, MACD, support/resistance) from `data/stage2/technicals.json`. Price history charts are rendered from `data/stage2/technicals.json` if a `price_history` key is present, but `stage2_technicals` does not currently populate this key; charts will show a "data unavailable" notice until the agent is extended to call `_get_price_history`.

## Important Notes

**Robinhood 2FA:** On a new machine or after session expiry, run `python login_robinhood.py` once interactively to complete 2FA and cache the session token. Subsequent pipeline runs reuse the cached token automatically.

**Alpha Vantage rate limit:** The free tier allows 5 requests per minute. `mcp_server.py` enforces a 13-second minimum interval between Alpha Vantage calls (`_AV_MIN_INTERVAL = 13.0`). The `stage1_news` agent calls this once per portfolio ticker, so large portfolios will slow this step proportionally.

**`--resume` flag:** If Stage 1 data is fresh and Stage 2/3 failed (e.g., Anthropic rate limit), use `orchestrator.py --resume` to skip re-fetching all market data. The orchestrator reads tickers from the existing `data/stage1/portfolio.json`.

**Retry behavior:** All agents are wrapped in a retry loop that catches HTTP 429 and rate-limit errors. Base delay is 65 seconds with exponential backoff, capped at 120 seconds, up to 5 attempts.

**Model and cost:** All Anthropic API calls use `claude-haiku-4-5-20251001`. Cost is computed at $0.80/M input tokens and $4.00/M output tokens and printed after each Stage 2/3 agent completes. Stage 1 has zero API cost.
