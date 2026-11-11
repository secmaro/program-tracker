"""
Program Tracker bot — main entry point.

Runs a FastAPI server with a /health endpoint (for UptimeRobot keep-alive pings)
and an APScheduler job that checks for new programs / scope changes every
15 minutes (configurable via CHECK_INTERVAL_MINUTES).
"""
import logging
import os
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
import uvicorn

# Load config — fail fast if env vars missing
from config import config
from scraper import fetch_programs
from state import load_state, save_state, diff_programs
from notifier import send_diff, send_startup_message, send_error_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("program-tracker")

app = FastAPI(title="Program Tracker", version="1.0")
scheduler = AsyncIOScheduler()


def run_check() -> None:
    """Single check cycle: fetch -> diff -> alert -> persist."""
    log.info("Starting check cycle")

    try:
        # 1. Fetch current Bugcrowd programs
        programs = fetch_programs()
    except Exception as e:
        log.exception("Fetch failed")
        send_error_message(f"Fetch failed: {e}")
        return

    try:
        # 2. Load previous state
        prev_state, gist_id = load_state()
    except Exception as e:
        log.exception("State load failed")
        send_error_message(f"State load failed: {e}")
        return

    # 3. First run: just save state, send startup message with counts
    is_first_run = not prev_state.get("programs")
    diff, new_state = diff_programs(programs, prev_state)

    if is_first_run:
        log.info("First run — saving baseline of %d programs", len(programs))
        try:
            save_state(new_state, gist_id)
            send_startup_message(gist_id=gist_id, program_count=len(programs))
        except Exception as e:
            log.exception("First-run save failed")
            send_error_message(f"First-run save failed: {e}")
        return

    # 4. Subsequent runs: alert on changes
    if diff.has_changes():
        n_new = len(diff.new_programs)
        n_scope = len(set(diff.scope_added) | set(diff.scope_removed))
        log.info(
            "Detected changes: %d new programs, %d scope changes",
            n_new, n_scope,
        )
        try:
            sent = send_diff(diff, all_programs=programs)
            log.info("Sent %d Telegram messages", sent)
        except Exception as e:
            log.exception("Telegram send failed")
            send_error_message(f"Telegram send failed: {e}")
    else:
        log.info("No changes detected")

    # 5. Persist new state
    try:
        save_state(new_state, gist_id)
    except Exception as e:
        log.exception("State save failed")
        send_error_message(f"State save failed: {e}")


@app.get("/")
@app.get("/health")
async def health() -> dict:
    """Health endpoint — UptimeRobot pings this every 10 min to prevent
    Render's free tier from spinning down."""
    return {
        "status": "ok",
        "check_interval_min": config.check_interval_minutes,
        "next_check": str(scheduler.get_job("check").next_run_time)
        if scheduler.get_job("check")
        else None,
    }


@app.on_event("startup")
async def startup() -> None:
    """Schedule periodic checks + run one immediately on boot."""
    scheduler.add_job(
        run_check,
        "interval",
        minutes=config.check_interval_minutes,
        id="check",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info(
        "Scheduler started — checking every %d min",
        config.check_interval_minutes,
    )
    # Run first check on boot so we don't wait 15 min for the first one
    scheduler.add_job(run_check, id="initial-check")


@app.on_event("shutdown")
async def shutdown() -> None:
    scheduler.shutdown(wait=False)


if __name__ == "__main__":
    # Render sets PORT env var; default to 8000 for local dev
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "bot:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
