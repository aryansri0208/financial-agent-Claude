"""Stage 3 — Synthesis Agent: merges all Stage 2 outputs into final analysis_output.json"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

S1 = os.path.join(ROOT, "data", "stage1")
S2 = os.path.join(ROOT, "data", "stage2")
OUTFILE = os.path.join(ROOT, "analysis_output.json")

PROMPT = f"""
You are the final synthesis agent. Produce ONE unified investment report.

Read these files (skip any that don't exist):
- {S1}/portfolio.json
- {S1}/macro.json
- {S2}/portfolio_analysis.json
- {S2}/opportunities.json
- {S2}/technicals.json

Produce a COMPACT JSON report and write it to {OUTFILE} using Write. Fields:

portfolio_summary: {{total_value, total_pl, total_pl_pct, health_score (1-10), assessment (1 sentence)}}
holds: [{{ticker, current_price, pl_pct, reason}}] — tickers to hold
sells: [{{ticker, exit_price_target, stop_loss, reasoning}}] — tickers to sell/reduce
new_buys: [{{type, ticker, entry_price_low, entry_price_high, price_target_12m, conviction, best_time_to_buy, reasoning}}]
watchlist: [{{ticker, reason}}]
macro_context: "2-3 sentences on macro environment"
strategy_summary: "1 paragraph overall strategy"
sources: {{market_data:[], macro:[], crypto:[], news:[], filings:[]}}

Keep reasoning fields to 1-2 sentences each. Keep the full JSON under 3000 tokens.
"""


async def run() -> dict:
    output = {}
    async for message in query(
        prompt=PROMPT,
        options=ClaudeAgentOptions(
            tools=["Read", "Write"],
            allowed_tools=["Read", "Write"],
            permission_mode="bypassPermissions",
            model="claude-haiku-4-5-20251001",
            cwd=ROOT,
            env={"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"]},
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text") and block.text:
                    print(f"[synthesis] {block.text[:120]}")
        elif isinstance(message, ResultMessage):
            output["status"] = message.subtype
            output["cost"] = message.total_cost_usd
    return output


if __name__ == "__main__":
    asyncio.run(run())
