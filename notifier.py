"""
Telegram notifier — sends formatted alerts via Bot API.
"""
import logging
from typing import List

import httpx

from config import config
from models import Program, ProgramDiff

log = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{config.telegram_bot_token}"

# Telegram MarkdownV2 reserved chars that must be escaped
_ESCAPE = r"_*[]()~`>#+-=|{}.!"


def _escape(text: str) -> str:
    """Escape MarkdownV2 reserved chars."""
    return "".join("\\" + c if c in _ESCAPE else c for c in text)


def _format_scope_block(domains: List[str], limit: int = 8) -> str:
    """Format a list of domains for Telegram. Caps at `limit` shown."""
    if not domains:
        return "_\\(no in\\-scope assets listed\\)_"
    shown = domains[:limit]
    rest = len(domains) - len(shown)
    lines = [f"  • {_escape(d)}" for d in sorted(shown)]
    if rest > 0:
        lines.append(f"  • _\\(\\+{rest} more\\)_")
    return "\n".join(lines)


def _send_message(text: str) -> bool:
    """Send a MarkdownV2 message to the configured chat."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": config.telegram_chat_id,
                    "text": text,
                    "parse_mode": "MarkdownV2",
                    "disable_web_page_preview": True,
                },
            )
        if resp.status_code != 200:
            log.error("Telegram API error: %s — %s", resp.status_code, resp.text)
            return False
        return True
    except Exception as e:
        log.exception("Failed to send Telegram message: %s", e)
        return False


def _program_url_for_slug(slug: str, known_url: str = "") -> str:
    """Best URL for a program. Use known_url if available, else build from slug."""
    if known_url:
        return known_url
    return f"https://bugcrowd.com/{slug}"


def _alert_new_program(prog: Program) -> str:
    url = _program_url_for_slug(prog.slug, prog.url)
    domains = sorted(prog.domains)
    return (
        "🆕 *NEW PROGRAM*\n"
        "━━━━━━━━━━━━━━━━\n"
        f"*Name:* {_escape(prog.name)}\n"
        f"*URL:* [{_escape(url)}]({_escape(url)})\n"
        f"*Scope \\({len(domains)} assets\\):*\n"
        f"{_format_scope_block(domains)}\n"
        "━━━━━━━━━━━━━━━━"
    )


def _alert_scope_change(
    slug: str,
    name: str,
    url: str,
    added: List[str],
    removed: List[str],
) -> str:
    parts = [
        "🔄 *SCOPE CHANGE*",
        "━━━━━━━━━━━━━━━━",
        f"*Program:* {_escape(name)}",
        f"*URL:* [{_escape(url)}]({_escape(url)})",
    ]

    if added:
        parts.append(f"*\\+ Added \\({len(added)}\\):*")
        parts.append(_format_scope_block(added, limit=15))

    if removed:
        parts.append(f"*\\- Removed \\({len(removed)}\\):*")
        parts.append(_format_scope_block(removed, limit=15))

    parts.append("━━━━━━━━━━━━━━━━")
    return "\n".join(parts)


def _lookup_program_name(prog: Program, slug: str) -> str:
    return prog.name if prog.slug == slug else slug.replace("-", " ").title()


def send_diff(diff: ProgramDiff, all_programs: List[Program]) -> int:
    """Send all alerts for a diff. Returns count of messages sent."""
    sent = 0
    # Build a quick lookup so scope-change alerts can include the program name+url
    prog_by_slug = {p.slug: p for p in all_programs}

    # 1. New programs (highest priority — send first)
    for prog in diff.new_programs:
        msg = _alert_new_program(prog)
        if _send_message(msg):
            sent += 1

    # 2. Scope changes
    all_changed_slugs = set(diff.scope_added.keys()) | set(diff.scope_removed.keys())
    for slug in sorted(all_changed_slugs):
        prog = prog_by_slug.get(slug)
        name = prog.name if prog else slug.replace("-", " ").title()
        url = prog.url if prog else _program_url_for_slug(slug)
        msg = _alert_scope_change(
            slug=slug,
            name=name,
            url=url,
            added=diff.scope_added.get(slug, []),
            removed=diff.scope_removed.get(slug, []),
        )
        if _send_message(msg):
            sent += 1

    return sent


def send_startup_message(gist_id: str, program_count: int) -> None:
    """Send a one-time message when the bot starts."""
    msg = (
        "✅ *Program Tracker started*\n"
        "━━━━━━━━━━━━━━━━\n"
        f"*State gist:* `{_escape(gist_id)}`\n"
        f"*Tracking:* {program_count} Bugcrowd programs\n"
        f"*Check interval:* every {config.check_interval_minutes} min\n"
        "━━━━━━━━━━━━━━━━\n"
        "_Save the gist ID above as GIST\\_ID env var "
        "so state persists across restarts\\._"
    )
    _send_message(msg)


def send_error_message(error: str) -> None:
    msg = (
        "⚠️ *Program Tracker error*\n"
        "━━━━━━━━━━━━━━━━\n"
        f"```\n{_escape(error[:1500])}\n```"
    )
    _send_message(msg)
