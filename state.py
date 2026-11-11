"""
State storage using GitHub Gist.

Why Gist?
- Render free tier has an ephemeral filesystem (wiped on every deploy)
- GitHub Gist is free, persistent, and has a stable REST API
- One file per bot instance: program-tracker-state.json

State schema (JSON):
{
  "last_check": "2026-11-11T10:00:00Z",
  "programs": {
    "<slug>": {
      "name": "Program Name",
      "url": "https://bugcrowd.com/slug",
      "domains": ["a.com", "b.com"]
    }
  }
}
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from config import config
from models import Program, ProgramDiff

log = logging.getLogger(__name__)

GIST_FILENAME = "program-tracker-state.json"
GIST_DESC = "Program Tracker state — auto-managed, do not edit manually"


def _gist_api(method: str, path: str, **kwargs) -> httpx.Response:
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {config.github_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": config.user_agent,
    }
    with httpx.Client(timeout=30) as client:
        return client.request(method, url, headers=headers, **kwargs)


def _create_gist(initial_content: dict) -> str:
    """Create a new secret gist with the initial state. Returns gist ID."""
    payload = {
        "description": GIST_DESC,
        "public": False,  # secret gist — keeps program list private
        "files": {
            GIST_FILENAME: {
                "content": json.dumps(initial_content, indent=2, default=str)
            }
        },
    }
    resp = _gist_api("POST", "/gists", json=payload)
    resp.raise_for_status()
    gist_id = resp.json()["id"]
    log.info("Created new gist: %s", gist_id)
    return gist_id


def _read_gist(gist_id: str) -> dict:
    """Read state from gist. Returns empty state if gist is new/empty."""
    resp = _gist_api("GET", f"/gists/{gist_id}")
    if resp.status_code == 404:
        log.warning("Gist %s not found — starting fresh", gist_id)
        return _empty_state()
    resp.raise_for_status()

    files = resp.json().get("files", {})
    file_obj = files.get(GIST_FILENAME)
    if not file_obj or not file_obj.get("content"):
        return _empty_state()

    try:
        return json.loads(file_obj["content"])
    except json.JSONDecodeError as e:
        log.error("State JSON corrupted: %s — starting fresh", e)
        return _empty_state()


def _write_gist(gist_id: str, state: dict) -> None:
    """Update the gist with new state."""
    payload = {
        "description": GIST_DESC,
        "files": {
            GIST_FILENAME: {
                "content": json.dumps(state, indent=2, default=str)
            }
        },
    }
    resp = _gist_api("PATCH", f"/gists/{gist_id}", json=payload)
    resp.raise_for_status()
    log.info("State persisted to gist %s", gist_id)


def _empty_state() -> dict:
    return {
        "last_check": None,
        "programs": {},
    }


def load_state() -> tuple[dict, Optional[str]]:
    """Load state from gist. Returns (state, gist_id).

    If GIST_ID env var is unset, creates a new gist and returns its ID.
    The caller should persist this ID (e.g. via Render env var or log it).
    """
    if config.gist_id:
        return _read_gist(config.gist_id), config.gist_id

    log.info("No GIST_ID set — creating new gist for state storage")
    state = _empty_state()
    gist_id = _create_gist(state)
    return state, gist_id


def save_state(state: dict, gist_id: str) -> None:
    """Persist state to gist."""
    _write_gist(gist_id, state)


def diff_programs(
    current_programs: List[Program], prev_state: dict
) -> tuple[ProgramDiff, dict]:
    """Compare current programs against previous state.

    Returns:
        (diff, new_state) — diff has new_programs + scope changes;
        new_state is ready to persist.
    """
    prev_programs: Dict[str, dict] = prev_state.get("programs", {})
    diff = ProgramDiff()

    new_state_programs: Dict[str, dict] = {}

    for prog in current_programs:
        # Always record current state
        new_state_programs[prog.slug] = {
            "name": prog.name,
            "url": prog.url,
            "domains": sorted(prog.domains),
        }

        prev = prev_programs.get(prog.slug)
        if prev is None:
            # Brand-new program
            diff.new_programs.append(prog)
            continue

        # Existing program — check scope change
        prev_domains = frozenset(d.lower().strip() for d in (prev.get("domains") or []))
        curr_domains = prog.domain_signature()

        added = sorted(curr_domains - prev_domains)
        removed = sorted(prev_domains - curr_domains)

        if added:
            diff.scope_added[prog.slug] = added
        if removed:
            diff.scope_removed[prog.slug] = removed

    new_state = {
        "last_check": datetime.now(timezone.utc).isoformat(),
        "programs": new_state_programs,
    }
    return diff, new_state
