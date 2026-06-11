# Architecture

The pipeline runs in three sequential stages. Stage 1 collects live market data from six external APIs using direct Python calls (no AI, zero cost). Stage 2 feeds that raw data into three Claude Haiku calls that produce structured analysis JSON files. Stage 3 merges everything into a single `analysis_output.json` with a final unified investment report.

```mermaid
graph TD
    A([run.py]) -->|full run| B[orchestrator.py]
    A -->|--dashboard-only| DASH
    B -->|--resume skips Stage 1| S2_START

    subgraph MCP ["mcp_server.py  (in-process, 13 _get_* functions)"]
        M1[_get_portfolio]
        M2[_get_stock_fundamentals\n_get_analyst_targets\n_get_insider_trades\n_get_institutional_holdings]
        M3[_get_macro_data\n_get_sector_performance]
        M4[_get_crypto_data\n_get_crypto_trending]
        M5[_get_news_and_sentiment]
        M6[_get_etf_info]
        M7[_get_technical_indicators]
    end

    subgraph S1 ["Stage 1 — Data Collection  (no Anthropic API, cost = $0)"]
        direction TB
        P1[stage1_portfolio] -->|calls| M1
        P2[stage1_fundamentals] -->|calls| M2
        P3[stage1_macro] -->|calls| M3
        P4[stage1_crypto] -->|calls| M4
        P5[stage1_news] -->|calls| M5
        P6[stage1_etf] -->|calls| M6

        P1 --> D1[data/stage1/portfolio.json]
        P2 --> D2[data/stage1/fundamentals.json]
        P3 --> D3[data/stage1/macro.json]
        P4 --> D4[data/stage1/crypto.json]
        P5 --> D5[data/stage1/news.json]
        P6 --> D6[data/stage1/etf.json]
    end

    subgraph EXT ["External APIs"]
        E1[(Robinhood)]
        E2[(Finnhub +\nYahoo Finance)]
        E3[(FRED +\nYahoo Finance)]
        E4[(CoinGecko)]
        E5[(Alpha Vantage +\nFinnhub)]
        E6[(Yahoo Finance)]
    end

    M1 --> E1
    M2 --> E2
    M3 --> E3
    M4 --> E4
    M5 --> E5
    M6 --> E6
    M7 --> E6

    B --> S1

    D1 & D2 & D5 & D3 --> A2
    D3 & D6 & D4 & D5 --> A3
    D1 -->|portfolio tickers| A4

    subgraph S2 ["Stage 2 — Analysis  (3 x Claude Haiku API call)"]
        S2_START[ ]:::hidden
        direction TB
        A2[stage2_portfolio_analysis] --> DA2[data/stage2/portfolio_analysis.json]
        A3[stage2_opportunities] --> DA3[data/stage2/opportunities.json]
        A4[stage2_technicals] -->|calls _get_technical_indicators| M7
        A4 --> DA4[data/stage2/technicals.json]
    end

    S2_START --> A2

    subgraph S3 ["Stage 3 — Synthesis  (1 x Claude Haiku API call)"]
        direction TB
        SYN[stage3_synthesis]
        SYN --> OUT[analysis_output.json]
    end

    D1 & D3 & DA2 & DA3 & DA4 --> SYN

    OUT --> DASH
    D1 & D2 & D3 & D4 & D5 & D6 & DA2 & DA4 --> DASH

    DASH([dashboard.py\nStreamlit UI])

    classDef hidden display:none
    classDef apiNode fill:#1e3a5f,stroke:#4a90d9,color:#cce4ff
    classDef dataFile fill:#1a3a1a,stroke:#4caf50,color:#c8e6c9
    classDef agent fill:#2d1b4e,stroke:#9c6ade,color:#e8d5ff
    classDef entry fill:#3a2a00,stroke:#f0a000,color:#fff8e1
    classDef dash fill:#1a2a3a,stroke:#00bcd4,color:#e0f7fa

    class E1,E2,E3,E4,E5,E6 apiNode
    class D1,D2,D3,D4,D5,D6,DA2,DA3,DA4,OUT dataFile
    class P1,P2,P3,P4,P5,P6,A2,A3,A4,SYN agent
    class A entry
    class DASH dash
```
