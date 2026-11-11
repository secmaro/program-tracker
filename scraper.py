"""
Scraper: fetches Bugcrowd programs from ProjectDiscovery's
community-maintained public-bugbounty-programs JSON.

Why this instead of scraping bugcrowd.com directly?
- Bugcrowd's site is JS-rendered (React) — plain HTTP gets empty HTML
- ProjectDiscovery's repo is updated daily by the community
- JSON is structured: name, url, domains, platform, bounty flag
- We filter to platform == "bugcrowd" only
"""
import httpx
import logging
from typing import List

from config import config
from models import Program

log = logging.getLogger(__name__)


def _slug_from_url(url: str) -> str:
    """Extract program slug from Bugcrowd URL.

    Examples:
        https://bugcrowd.com/acme-corp -> acme-corp
        https://bugcrowd.com/acme-corp?utm=x -> acme-corp
    """
    # Strip protocol + query
    path = url.split("bugcrowd.com/", 1)[-1]
    path = path.split("?", 1)[0].split("#", 1)[0]
    return path.strip("/").split("/", 1)[0]


def fetch_programs() -> List[Program]:
    """Fetch all Bugcrowd programs from ProjectDiscovery data source.

    Returns:
        List of Program objects, platform-filtered to bugcrowd only.
    """
    log.info("Fetching bug bounty program data from %s", config.data_source_url)
    headers = {"User-Agent": config.user_agent}

    with httpx.Client(timeout=60, headers=headers) as client:
        resp = client.get(config.data_source_url)
        resp.raise_for_status()
        data = resp.json()

    # The JSON structure is: { "programs": [ {name, url, bounty, domains, ...}, ... ] }
    raw_programs = data.get("programs", [])
    log.info("Got %d total programs across all platforms", len(raw_programs))

    programs: List[Program] = []
    seen_slugs = set()

    for entry in raw_programs:
        # ProjectDiscovery uses "program_url" or "url" — handle both
        url = entry.get("program_url") or entry.get("url") or ""
        if "bugcrowd.com" not in url.lower():
            continue

        # Some entries disable bounty (swag only or VDP). We include them all
        # since the user picked "alert everything" — no filtering.
        name = entry.get("name", "").strip() or "(unnamed program)"
        slug = _slug_from_url(url)

        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Domains: list of in-scope assets. Some programs have empty scope
        # in ProjectDiscovery data — we still track them so scope additions
        # trigger alerts later.
        domains = [d.strip() for d in (entry.get("domains") or []) if d.strip()]

        programs.append(
            Program(
                slug=slug,
                name=name,
                url=url,
                domains=domains,
                platform="bugcrowd",
            )
        )

    log.info("Filtered to %d Bugcrowd programs", len(programs))
    return programs
