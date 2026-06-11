"""
Multi-stage portfolio advisor pipeline.

Stage 1: 6 data collection agents run in parallel
Stage 2: 3 analysis agents run in parallel (fed Stage 1 JSON)
Stage 3: 1 synthesis agent produces final analysis_output.json
"""
import asyncio
import json
import os
import sys
import time

from dotenv import load_dotenv

# Ensure project root is on path
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# Load API keys before agent imports (Anthropic, Robinhood, Finnhub, etc.)
load_dotenv(os.path.join(ROOT, ".env"))


async def _with_retry(label: str, coro_fn, *args, max_retries: int = 5, base_delay: float = 65.0):
    """Run an agent coroutine with exponential backoff on rate-limit errors.

    The SDK wraps all API-level 429s as `Exception("Claude Code returned an
    error result: success")`, so we treat any SDK error result as a potential
    rate-limit hit and retry — the model prints the 429 details to stdout
    before the SDK raises.
    """
    for attempt in range(max_retries):
        try:
            return await coro_fn(*args)
        except Exception as e:
            err_str = str(e).lower()
            # The SDK raises "error result: success" for all API errors (including 429).
            # Also catch explicit 429 / rate-limit keywords just in case.
            is_retryable = (
                "error result" in err_str
                or "429" in err_str
                or "rate limit" in err_str
                or "rate_limit" in err_str
            )
            if is_retryable and attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt)
                print(f"\n⚠️  [{label}] API error (likely rate limit) — waiting {wait:.0f}s before retry {attempt+1}/{max_retries-1}...")
                await asyncio.sleep(wait)
            else:
                print(f"\n❌  [{label}] Failed after {attempt+1} attempt(s): {e}")
                return {"status": "error", "cost": 0, "error": str(e)}
    return {"status": "error", "cost": 0}

from agents.stage1_portfolio import run as run_portfolio
from agents.stage1_fundamentals import run as run_fundamentals
from agents.stage1_macro import run as run_macro
from agents.stage1_crypto import run as run_crypto
from agents.stage1_news import run as run_news
from agents.stage1_etf import run as run_etf

from agents.stage2_portfolio_analysis import run as run_portfolio_analysis
from agents.stage2_opportunities import run as run_opportunities
from agents.stage2_technicals import run as run_technicals

from agents.stage3_synthesis import run as run_synthesis


def _load_json(path: str) -> dict:
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return {}
    with open(full) as f:
        return json.load(f)


def _get_tickers_from_portfolio() -> list[str]:
    data = _load_json("data/stage1/portfolio.json")
    return [h["ticker"] for h in data.get("holdings", [])]


def _print_stage(label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")



def _clean_data_dirs():
    """Remove all stage JSON files so Write tool can create them fresh."""
    import glob
    for pattern in [
        os.path.join(ROOT, "data", "stage1", "*.json"),
        os.path.join(ROOT, "data", "stage2", "*.json"),
        os.path.join(ROOT, "analysis_output.json"),
    ]:
        for f in glob.glob(pattern):
            os.remove(f)
    os.makedirs(os.path.join(ROOT, "data", "stage1"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "data", "stage2"), exist_ok=True)


async def run_pipeline():
    total_cost = 0.0
    start = time.time()

    print("\nCleaning old data files so agents can write fresh...")
    _clean_data_dirs()

    # ── Stage 1 ───────────────────────────────────────────────────
    _print_stage("STAGE 1: Data Collection (parallel)")

    # Portfolio runs first alone so we can extract tickers for other agents
    print("\n[Stage 1] Fetching Robinhood portfolio...")
    portfolio_result = await _with_retry("portfolio", run_portfolio)
    total_cost += portfolio_result.get("cost", 0) or 0

    tickers = _get_tickers_from_portfolio()
    if not tickers:
        raise RuntimeError(
            "Portfolio fetch returned no holdings. Check Robinhood credentials in .env "
            "and confirm the portfolio agent wrote data/stage1/portfolio.json correctly."
        )

    print(f"\n[Stage 1] Portfolio tickers: {tickers}")
    print("[Stage 1] Running data agents sequentially to respect rate limits...")

    # Sequential to stay within per-minute input/output token budgets
    COOLDOWN = 30  # seconds between agents to let token buckets refill
    for label, fn, fn_args in [
        ("fundamentals", run_fundamentals, (tickers,)),
        ("macro",        run_macro,        ()),
        ("crypto",       run_crypto,       ()),
        ("news",         run_news,         (tickers,)),
        ("etf",          run_etf,          ()),
    ]:
        print(f"\n▶  [{label}] starting...")
        r = await _with_retry(label, fn, *fn_args)
        total_cost += r.get("cost", 0) or 0
        print(f"  ✅  [{label}] done — cost so far: ${total_cost:.4f}")
        print(f"  ⏳  Cooling down {COOLDOWN}s before next agent...")
        await asyncio.sleep(COOLDOWN)

    _print_stage("STAGE 1 COMPLETE")

    # ── Stage 2 ───────────────────────────────────────────────────
    print(f"\n⏳  Waiting 65s for rate-limit buckets to reset before Stage 2...")
    await asyncio.sleep(65)
    _print_stage("STAGE 2: Analysis (sequential)")

    for label, fn in [
        ("portfolio_analysis", run_portfolio_analysis),
        ("opportunities",      run_opportunities),
        ("technicals",         run_technicals),
    ]:
        print(f"\n▶  [{label}] starting...")
        r = await _with_retry(label, fn)
        total_cost += r.get("cost", 0) or 0
        print(f"  ✅  [{label}] done — cost so far: ${total_cost:.4f}")
        print(f"  ⏳  Cooling down {COOLDOWN}s before next agent...")
        await asyncio.sleep(COOLDOWN)

    _print_stage("STAGE 2 COMPLETE")

    # ── Stage 3 ───────────────────────────────────────────────────
    print(f"\n⏳  Waiting 65s for rate-limit buckets to reset before Stage 3...")
    await asyncio.sleep(65)
    _print_stage("STAGE 3: Synthesis")

    synthesis_result = await _with_retry("synthesis", run_synthesis)
    total_cost += synthesis_result.get("cost", 0) or 0

    elapsed = round(time.time() - start, 1)
    _print_stage(f"PIPELINE COMPLETE — {elapsed}s — ${total_cost:.4f} total cost")

    output_path = os.path.join(ROOT, "analysis_output.json")
    if os.path.exists(output_path):
        print(f"\nFinal report written to: {output_path}")
    else:
        print("\nWARNING: analysis_output.json was not created.")

    return total_cost


if __name__ == "__main__":
    asyncio.run(run_pipeline())
