"""Stage 1 — News & Sentiment Agent: fetches Finnhub news and sentiment per ticker"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

MCP_CONFIG = {
    "finance": {
        "type": "stdio",
        "command": sys.executable,
        "args": [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_server.py")],
    }
}


OUTFILE = os.path.join(ROOT, "data", "stage1", "news.json")


def build_prompt(tickers: list[str]) -> str:
    ticker_list = ", ".join(tickers)
    return f"""
You are a data collection agent. Fetch news and sentiment data.

Steps:
1. For each ticker in [{ticker_list}], call get_news_and_sentiment.
2. For each ticker keep: bullish_pct, bearish_pct, sentiment_score, article_mentions_7d,
   and the top 3 articles. Each article: headline, source, url, sentiment_label (if present).
3. Also keep the top-level "sources" array from each tool response.
4. Combine into a compact JSON object. Use EACH TICKER as a top-level key directly
   (e.g. {{"NVDA": {{...}}, "AAPL": {{...}}, "sources": [...]}}). Do NOT wrap in a "data" key.
5. Write to {OUTFILE} using Write. Keep JSON compact, no extra whitespace.

Do not analyze. Just fetch and save.
"""


async def run(tickers: list[str]) -> dict:
    output = {}
    async for message in query(
        prompt=build_prompt(tickers),
        options=ClaudeAgentOptions(
            tools=["Write", "mcp__finance__get_news_and_sentiment"],
            allowed_tools=["mcp__finance__get_news_and_sentiment", "Write"],
            permission_mode="bypassPermissions",
            mcp_servers=MCP_CONFIG,
            model="claude-haiku-4-5-20251001",
            cwd=ROOT,
            env={"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"]},
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text") and block.text:
                    print(f"[news] {block.text[:120]}")
        elif isinstance(message, ResultMessage):
            output["status"] = message.subtype
            output["cost"] = message.total_cost_usd
    return output


if __name__ == "__main__":
    asyncio.run(run(["AAPL", "MSFT", "NVDA"]))
