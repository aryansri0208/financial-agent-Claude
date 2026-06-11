"""
Multi-stage portfolio advisor pipeline.

Stage 1 : 6 data-collection agents  (portfolio runs first, then 5 sequentially)
Stage 2 : 3 analysis agents          (sequential with cooldown)
Stage 3 : 1 synthesis agent

Enhanced with:
  - Rich progress bar (10 steps)
  - Per-agent start / finish notifications
  - API-pull confirmation (from each agent's output JSON)
  - Full log written to pipeline.log
"""
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

# ── Rich setup ────────────────────────────────────────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich import box

LOG_FILE = os.path.join(ROOT, "pipeline.log")
console = Console(highlight=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")],
    force=True,
)
log = logging.getLogger("pipeline")


# ── Pipeline step registry ────────────────────────────────────────────────────
#  (stage_label, agent_name, data_sources_hint)
STEPS = [
    ("Stage 1", "portfolio",          "Robinhood"),
    ("Stage 1", "fundamentals",       "Finnhub + Yahoo Finance"),
    ("Stage 1", "macro",              "FRED + Yahoo Finance"),
    ("Stage 1", "crypto",             "CoinGecko"),
    ("Stage 1", "news",               "Alpha Vantage + Finnhub"),
    ("Stage 1", "etf",                "Yahoo Finance"),
    ("Stage 2", "portfolio_analysis", "Stage-1 data"),
    ("Stage 2", "opportunities",      "Stage-1 data"),
    ("Stage 2", "technicals",         "Yahoo Finance"),
    ("Stage 3", "synthesis",          "Stage-1 + Stage-2 data"),
]
TOTAL = len(STEPS)

# JSON output path for each agent (to extract API source confirmations)
_AGENT_OUTPUT = {
    "portfolio":          os.path.join(ROOT, "data", "stage1", "portfolio.json"),
    "fundamentals":       os.path.join(ROOT, "data", "stage1", "fundamentals.json"),
    "macro":              os.path.join(ROOT, "data", "stage1", "macro.json"),
    "crypto":             os.path.join(ROOT, "data", "stage1", "crypto.json"),
    "news":               os.path.join(ROOT, "data", "stage1", "news.json"),
    "etf":                os.path.join(ROOT, "data", "stage1", "etf.json"),
    "portfolio_analysis": os.path.join(ROOT, "data", "stage2", "portfolio_analysis.json"),
    "opportunities":      os.path.join(ROOT, "data", "stage2", "opportunities.json"),
    "technicals":         os.path.join(ROOT, "data", "stage2", "technicals.json"),
    "synthesis":          os.path.join(ROOT, "analysis_output.json"),
}


# ── Notification helpers ──────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def notify_start(agent: str, step: int, apis: str):
    msg = f"▶  [{step}/{TOTAL}] {agent}  ({apis})"
    console.print(f"[bold cyan]{msg}[/bold cyan]  [dim]{_ts()}[/dim]")
    log.info(f"START  {msg}")


def notify_finish(agent: str, step: int, status: str, cost: float, elapsed: float, sources: list[str]):
    ok = status == "success"
    icon = "✅" if ok else "❌"
    color = "green" if ok else "red"
    src_str = ", ".join(sources) if sources else "—"
    console.print(
        f"[bold {color}]{icon} [{step}/{TOTAL}] {agent}[/bold {color}]"
        f"  status=[bold]{status}[/bold]"
        f"  cost=[yellow]${cost:.4f}[/yellow]"
        f"  [dim]{elapsed:.1f}s  {_ts()}[/dim]"
    )
    if sources:
        console.print(f"   [dim]APIs confirmed: {src_str}[/dim]")
    log.info(
        f"FINISH [{step}/{TOTAL}] {agent}  status={status}"
        f"  cost=${cost:.4f}  elapsed={elapsed:.1f}s"
        f"  apis={src_str}"
    )


def _read_sources(agent: str) -> list[str]:
    path = _AGENT_OUTPUT.get(agent, "")
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        # Collect "sources" from top-level or one level deep (fundamentals has per-ticker)
        raw: list[dict] = data.get("sources", [])
        if not raw:
            for v in data.values():
                if isinstance(v, dict):
                    raw.extend(v.get("sources", []))
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            raw.extend(item.get("sources", []))
        seen: set[str] = set()
        names: list[str] = []
        for s in raw:
            n = s.get("source_name") or s.get("name") or ""
            if n and n not in seen:
                seen.add(n)
                names.append(n)
        return names
    except Exception:
        return []


# ── Retry wrapper ─────────────────────────────────────────────────────────────

async def _with_retry(label: str, coro_fn, *args, max_retries: int = 5, base_delay: float = 65.0, max_delay: float = 120.0):
    for attempt in range(max_retries):
        try:
            return await coro_fn(*args)
        except Exception as e:
            err_str = str(e).lower()
            is_retryable = (
                "error result" in err_str
                or "429" in err_str
                or "rate limit" in err_str
                or "rate_limit" in err_str
            )
            if is_retryable and attempt < max_retries - 1:
                wait = min(base_delay * (2 ** attempt), max_delay)
                console.print(f"[yellow]⚠  [{label}] rate-limit — retrying in {wait:.0f}s (attempt {attempt+1})[/yellow]")
                log.warning(f"RATE_LIMIT [{label}] waiting {wait:.0f}s before retry {attempt+1}/{max_retries-1}")
                await asyncio.sleep(wait)
            else:
                console.print(f"[red]❌  [{label}] failed after {attempt+1} attempt(s): {e}[/red]")
                log.error(f"FAILED [{label}] after {attempt+1} attempts: {e}")
                return {"status": "error", "cost": 0, "error": str(e)}
    return {"status": "error", "cost": 0}


# ── Agent imports ─────────────────────────────────────────────────────────────
from agents.stage1_portfolio    import run as run_portfolio
from agents.stage1_fundamentals import run as run_fundamentals
from agents.stage1_macro        import run as run_macro
from agents.stage1_crypto       import run as run_crypto
from agents.stage1_news         import run as run_news
from agents.stage1_etf          import run as run_etf

from agents.stage2_portfolio_analysis import run as run_portfolio_analysis
from agents.stage2_opportunities      import run as run_opportunities
from agents.stage2_technicals         import run as run_technicals

from agents.stage3_synthesis import run as run_synthesis


# ── Utilities ─────────────────────────────────────────────────────────────────

def _load_json(path: str) -> dict:
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return {}
    with open(full) as f:
        return json.load(f)


def _get_tickers() -> list[str]:
    data = _load_json("data/stage1/portfolio.json")
    return [h["ticker"] for h in data.get("holdings", [])]


def _clean_data_dirs():
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


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_pipeline(resume: bool = False):
    total_cost = 0.0
    pipeline_start = time.time()

    log.info("=" * 70)
    log.info("PIPELINE %s  %s", "RESUME" if resume else "START", datetime.now().isoformat())
    log.info("=" * 70)

    console.print(Panel.fit(
        "[bold white]Portfolio Advisor — Multi-Agent Pipeline[/bold white]\n"
        f"[dim]Mode    : {'RESUME from Stage 2' if resume else 'Full run'}[/dim]\n"
        f"[dim]Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]\n"
        f"[dim]Log file: {LOG_FILE}[/dim]",
        border_style="bright_blue",
        padding=(0, 2),
    ))

    if not resume:
        console.print(f"\nCleaning stale data files…")
        log.info("Cleaning stale data files")
        _clean_data_dirs()

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
        expand=True,
    ) as progress:
        completed = 6 if resume else 0
        overall = progress.add_task("Overall pipeline", total=TOTAL, completed=completed)

        async def run_step(step_idx: int, agent: str, fn, fn_args: tuple):
            nonlocal total_cost
            _, _, apis = STEPS[step_idx - 1]
            notify_start(agent, step_idx, apis)
            progress.update(overall, description=f"[bold blue]{agent}")
            t0 = time.time()
            r = await _with_retry(agent, fn, *fn_args)
            elapsed = round(time.time() - t0, 1)
            cost = r.get("cost", 0) or 0
            total_cost += cost
            sources = _read_sources(agent)
            notify_finish(agent, step_idx, r.get("status", "error"), cost, elapsed, sources)
            progress.advance(overall)
            return r

        if not resume:
            # ── Stage 1 ───────────────────────────────────────────────────────
            console.print(Rule("[bold magenta]STAGE 1 — Data Collection[/bold magenta]"))
            log.info("--- STAGE 1: Data Collection ---")

            await run_step(1, "portfolio", run_portfolio, ())

            tickers = _get_tickers()
            if not tickers:
                raise RuntimeError(
                    "Portfolio fetch returned no holdings. "
                    "Check Robinhood credentials in .env and verify portfolio.json was written."
                )
            console.print(f"[dim]Tickers in portfolio: {', '.join(tickers)}[/dim]")
            log.info("Portfolio tickers: %s", tickers)

            for step_idx, agent, fn, fn_args in [
                (2, "fundamentals", run_fundamentals, (tickers,)),
                (3, "macro",        run_macro,        ()),
                (4, "crypto",       run_crypto,       ()),
                (5, "news",         run_news,         (tickers,)),
                (6, "etf",          run_etf,          ()),
            ]:
                await run_step(step_idx, agent, fn, fn_args)

            console.print(Rule("[bold green]STAGE 1 COMPLETE[/bold green]"))
            log.info("--- STAGE 1 COMPLETE ---")
        else:
            tickers = _get_tickers()
            console.print(Rule("[bold yellow]RESUMING FROM STAGE 2[/bold yellow]"))
            console.print(f"[dim]Tickers: {', '.join(tickers)}[/dim]")
            log.info("Resuming from Stage 2. Tickers: %s", tickers)

        # ── Stage 2 ───────────────────────────────────────────────────────────
        console.print(Rule("[bold magenta]STAGE 2 — Analysis[/bold magenta]"))
        log.info("--- STAGE 2: Analysis ---")

        for step_idx, agent, fn in [
            (7, "portfolio_analysis", run_portfolio_analysis),
            (8, "opportunities",      run_opportunities),
            (9, "technicals",         run_technicals),
        ]:
            await run_step(step_idx, agent, fn, ())

        console.print(Rule("[bold green]STAGE 2 COMPLETE[/bold green]"))
        log.info("--- STAGE 2 COMPLETE ---")

        # ── Stage 3 ───────────────────────────────────────────────────────────
        console.print(Rule("[bold magenta]STAGE 3 — Synthesis[/bold magenta]"))
        log.info("--- STAGE 3: Synthesis ---")
        await run_step(10, "synthesis", run_synthesis, ())

        progress.update(overall, description="[bold green]Pipeline complete")

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed_total = round(time.time() - pipeline_start, 1)
    output_path = os.path.join(ROOT, "analysis_output.json")
    report_ok = os.path.exists(output_path)

    console.print(Panel.fit(
        f"[bold green]PIPELINE COMPLETE[/bold green]\n"
        f"Total time  : [yellow]{elapsed_total}s[/yellow]\n"
        f"Total cost  : [yellow]${total_cost:.4f}[/yellow]\n"
        f"Final report: [cyan]{output_path if report_ok else 'NOT CREATED — check logs'}[/cyan]",
        border_style="green",
        padding=(0, 2),
    ))

    log.info("PIPELINE COMPLETE  elapsed=%.1fs  total_cost=$%.4f  report_ok=%s",
             elapsed_total, total_cost, report_ok)

    if not report_ok:
        console.print("[red]WARNING: analysis_output.json was not created. Check pipeline.log for errors.[/red]")

    return total_cost


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="Skip Stage 1 and resume from Stage 2")
    args = parser.parse_args()
    asyncio.run(run_pipeline(resume=args.resume))
