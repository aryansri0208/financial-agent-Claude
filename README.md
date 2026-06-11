# Financial Agent

AI-powered portfolio advisor that collects live market data, analyzes holdings, and synthesizes investment recommendations via a multi-stage agent pipeline.

## What it does

- Pulls your live Robinhood portfolio — positions, quantities, average cost, and current prices.
- Fetches fundamentals (P/E, EPS, beta, revenue growth, profit margin, debt-to-equity, ROE) via Finnhub and Yahoo Finance.
- Collects macroeconomic indicators from FRED (Fed rate, CPI, yield curve, unemployment) and sector ETF performance from Yahoo Finance.
- Retrieves crypto market data from CoinGecko and news sentiment scores from Alpha Vantage (with Finnhub and VADER as fallbacks).
- Runs four Claude Haiku calls total: three analysis calls (portfolio holdings, new opportunities, technical levels) plus one synthesis call that merges everything into a single investment report.
- Displays the results in an interactive Streamlit dashboard with charts, technical overlays, and a full source trace.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for a Mermaid flowchart of the full pipeline.

The pipeline runs in three sequential stages:

- **Stage 1 — Data Collection**: Six agents call `mcp_server.py` functions in-process to fetch raw data from six external APIs. No AI is used; cost is $0.
- **Stage 2 — Analysis**: Three agents each make one Claude Haiku call to analyze portfolio holdings, identify new opportunities, and compute technical levels.
- **Stage 3 — Synthesis**: One Claude Haiku call merges all Stage 1 and Stage 2 JSON into a unified `analysis_output.json` report.

## Setup

### Requirements

- Python 3.11 or later
- A Robinhood account with API access
- API keys for Anthropic, Finnhub, Alpha Vantage, and FRED

### Install

```bash
git clone <repo-url>
cd financial-agent-Claude
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment variables

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...your key...
ROBINHOOD_USERNAME=...your Robinhood email...
ROBINHOOD_PASSWORD=...your Robinhood password...
FINNHUB_API_KEY=...your Finnhub key...
ALPHA_VANTAGE_API_KEY=...your Alpha Vantage key...
FRED_API_KEY=...your FRED key...
```

### First-time Robinhood login

Robinhood requires device verification on the first login. Run this once to complete the flow and cache a session token locally:

```bash
python login_robinhood.py
```

## Usage

### Full run (pipeline + dashboard)

Runs all three pipeline stages and then launches the Streamlit dashboard:

```bash
python run.py
```

### Pipeline only

Runs all three stages without launching the dashboard:

```bash
python orchestrator.py
```

### Resume from Stage 2

Skips Stage 1 data collection and re-runs only the AI analysis stages. Use this when Stage 1 data is already fresh:

```bash
python orchestrator.py --resume
```

### Dashboard only

Launches the dashboard against the most recent `analysis_output.json` without re-running the pipeline:

```bash
python run.py --dashboard-only
```

### Dashboard direct

```bash
streamlit run dashboard.py
```

## External APIs

| API | Used for |
|-----|----------|
| Robinhood | Portfolio holdings, positions, prices |
| Finnhub | Fundamentals (company profile, financial metrics), news articles (fallback when Alpha Vantage unavailable) |
| Yahoo Finance | Prices, ETF data, technical indicators (SMA, RSI, MACD), price history, sector performance |
| FRED | Fed funds rate, CPI, unemployment, Treasury yields |
| CoinGecko | Crypto prices, market caps, trending coins |
| Alpha Vantage | News and sentiment scores (primary; falls back to Finnhub + VADER) |
| Anthropic Claude Haiku | AI analysis in Stage 2 and Stage 3 |

## Cost

Stage 1 makes no AI calls and costs **$0**.

Stage 2 and Stage 3 make four Claude Haiku calls total (three analysis calls and one synthesis call). A full run costs approximately **$0.03 – $0.05** depending on portfolio size.

## Project structure

```
financial-agent-Claude/
├── run.py                        # Entry point: pipeline + dashboard
├── orchestrator.py               # Pipeline runner (Stages 1-3), --resume flag
├── mcp_server.py                 # 13 in-process data-fetch functions
├── dashboard.py                  # Streamlit dashboard
├── login_robinhood.py            # One-time Robinhood device verification
├── requirements.txt
├── .env                          # API credentials (not committed)
├── analysis_output.json          # Final report (generated)
├── pipeline.log                  # Run log (generated)
├── docs/
│   └── architecture.md           # Mermaid architecture diagram
├── agents/
│   ├── stage1_portfolio.py
│   ├── stage1_fundamentals.py
│   ├── stage1_macro.py
│   ├── stage1_crypto.py
│   ├── stage1_news.py
│   ├── stage1_etf.py
│   ├── stage2_portfolio_analysis.py
│   ├── stage2_opportunities.py
│   ├── stage2_technicals.py
│   └── stage3_synthesis.py
└── data/
    ├── stage1/                   # Raw JSON from Stage 1 agents (generated)
    └── stage2/                   # Analysis JSON from Stage 2 agents (generated)
```
