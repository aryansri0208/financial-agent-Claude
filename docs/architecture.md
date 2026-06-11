# Architecture

The pipeline runs in three sequential stages. Stage 1 collects live market data from six external APIs using direct Python calls (no AI, zero cost). Stage 2 feeds that raw data into three Claude Haiku calls that produce structured analysis JSON files. Stage 3 merges everything into a single `analysis_output.json` with a final unified investment report.

```mermaid
graph TD
    RUN([run.py])
    ORCH[orchestrator.py]
    DASH([dashboard.py — Streamlit UI])

    RUN -->|full run| ORCH
    RUN -->|--dashboard-only| DASH

    subgraph S1 ["Stage 1 — Data Collection  (direct Python, cost = $0)"]
        P1[stage1_portfolio] --> D1[portfolio.json]
        P2[stage1_fundamentals] --> D2[fundamentals.json]
        P3[stage1_macro] --> D3[macro.json]
        P4[stage1_crypto] --> D4[crypto.json]
        P5[stage1_news] --> D5[news.json]
        P6[stage1_etf] --> D6[etf.json]
    end

    subgraph EXT ["External APIs"]
        E1[(Robinhood)]
        E2[(Finnhub + Yahoo Finance)]
        E3[(FRED + Yahoo Finance)]
        E4[(CoinGecko)]
        E5[(Alpha Vantage + Finnhub)]
        E6[(Yahoo Finance)]
    end

    P1 --> E1
    P2 --> E2
    P3 --> E3
    P4 --> E4
    P5 --> E5
    P6 --> E6

    ORCH --> S1

    subgraph S2 ["Stage 2 — Analysis  (3 × Claude Haiku API call)"]
        A2[stage2_portfolio_analysis] --> DA2[portfolio_analysis.json]
        A3[stage2_opportunities] --> DA3[opportunities.json]
        A4[stage2_technicals] --> DA4[technicals.json]
    end

    D1 --> A2
    D2 --> A2
    D3 --> A2
    D5 --> A2

    D3 --> A3
    D4 --> A3
    D5 --> A3
    D6 --> A3

    D1 --> A4
    A4 -->|_get_technical_indicators| E6

    ORCH -->|--resume starts here| S2

    subgraph S3 ["Stage 3 — Synthesis  (1 × Claude Haiku API call)"]
        SYN[stage3_synthesis] --> OUT[analysis_output.json]
    end

    D1 --> SYN
    D3 --> SYN
    DA2 --> SYN
    DA3 --> SYN
    DA4 --> SYN

    OUT --> DASH
    D1 --> DASH
    D2 --> DASH
    D3 --> DASH
    D4 --> DASH
    D5 --> DASH
    D6 --> DASH
    DA2 --> DASH
    DA4 --> DASH
```

## File locations

| Path | Written by | Read by |
|---|---|---|
| `data/stage1/portfolio.json` | stage1_portfolio | stage2_portfolio_analysis, stage2_technicals, stage3_synthesis, dashboard |
| `data/stage1/fundamentals.json` | stage1_fundamentals | stage2_portfolio_analysis, dashboard |
| `data/stage1/macro.json` | stage1_macro | stage2_portfolio_analysis, stage2_opportunities, stage3_synthesis |
| `data/stage1/crypto.json` | stage1_crypto | stage2_opportunities |
| `data/stage1/news.json` | stage1_news | stage2_portfolio_analysis, stage2_opportunities |
| `data/stage1/etf.json` | stage1_etf | stage2_opportunities |
| `data/stage2/portfolio_analysis.json` | stage2_portfolio_analysis | stage3_synthesis, dashboard |
| `data/stage2/opportunities.json` | stage2_opportunities | stage3_synthesis |
| `data/stage2/technicals.json` | stage2_technicals | stage3_synthesis, dashboard |
| `analysis_output.json` | stage3_synthesis | dashboard |

## mcp_server.py — 13 `_get_*` functions

| Function | External API | Used by |
|---|---|---|
| `_get_portfolio()` | Robinhood | stage1_portfolio |
| `_get_stock_fundamentals(ticker)` | Finnhub + Yahoo Finance | stage1_fundamentals |
| `_get_analyst_targets(ticker)` | Finnhub (premium) | unused — 403 on free tier |
| `_get_insider_trades(ticker)` | Finnhub (premium) | unused — 403 on free tier |
| `_get_institutional_holdings(ticker)` | Finnhub (premium) | unused — 403 on free tier |
| `_get_macro_data()` | FRED + Yahoo Finance | stage1_macro |
| `_get_sector_performance()` | Yahoo Finance | stage1_macro |
| `_get_crypto_data(coin_id)` | CoinGecko | stage1_crypto |
| `_get_crypto_trending()` | CoinGecko | stage1_crypto |
| `_get_news_and_sentiment(ticker)` | Alpha Vantage + Finnhub | stage1_news |
| `_get_etf_info(ticker)` | Yahoo Finance | stage1_etf |
| `_get_technical_indicators(ticker)` | Yahoo Finance | stage2_technicals |
| `_get_price_history(ticker)` | Yahoo Finance | unused — wired but not called |
