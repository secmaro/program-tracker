"""
Local test — verifies scraper + diff logic without needing real secrets.

Run:  python test_locally.py
"""
import json
import os
import sys

# Stub out the env vars config requires, so we can import the modules
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")
os.environ.setdefault("GITHUB_TOKEN", "test_token")

from scraper import fetch_programs, _slug_from_url
from state import diff_programs
from models import Program, ProgramDiff


def test_slug_extraction():
    """Verify URL -> slug extraction."""
    cases = [
        ("https://bugcrowd.com/acorns", "acorns"),
        ("https://bugcrowd.com/arrow-electronics-vdp", "arrow-electronics-vdp"),
        ("https://bugcrowd.com/asana?utm=foo", "asana"),
        ("https://bugcrowd.com/foo/bar", "foo"),
    ]
    for url, expected in cases:
        got = _slug_from_url(url)
        assert got == expected, f"slug({url!r}) = {got!r}, expected {expected!r}"
    print("PASS: slug extraction")


def test_real_fetch():
    """Hit the real data source and verify we get Bugcrowd programs back."""
    programs = fetch_programs()
    assert len(programs) > 50, f"Expected 50+ Bugcrowd programs, got {len(programs)}"
    for p in programs[:5]:
        assert "bugcrowd.com" in p.url, f"Non-bugcrowd URL leaked: {p.url}"
        assert p.slug, f"Empty slug for {p}"
        assert p.name, f"Empty name for {p}"
    print(f"PASS: real fetch — got {len(programs)} Bugcrowd programs")
    print(f"  Sample: {programs[0].name} -> {programs[0].url} ({len(programs[0].domains)} domains)")


def test_diff_new_program():
    """Verify a brand-new program triggers a 'new program' alert."""
    prev_state = {"programs": {}}
    current = [
        Program(slug="acorns", name="Acorns Grow", url="https://bugcrowd.com/acorns",
                domains=["acorns.com"], platform="bugcrowd"),
    ]
    diff, new_state = diff_programs(current, prev_state)
    assert len(diff.new_programs) == 1, "Should detect 1 new program"
    assert diff.new_programs[0].slug == "acorns"
    assert not diff.scope_added
    assert not diff.scope_removed
    assert "acorns" in new_state["programs"]
    print("PASS: new program diff")


def test_diff_scope_added():
    """Verify a scope addition triggers a 'scope change' alert."""
    prev_state = {
        "programs": {
            "acorns": {
                "name": "Acorns Grow",
                "url": "https://bugcrowd.com/acorns",
                "domains": ["acorns.com"],
            }
        }
    }
    current = [
        Program(slug="acorns", name="Acorns Grow", url="https://bugcrowd.com/acorns",
                domains=["acorns.com", "api.acorns.com", "staging.acorns.com"],
                platform="bugcrowd"),
    ]
    diff, _ = diff_programs(current, prev_state)
    assert not diff.new_programs, "Should not detect new program"
    assert "acorns" in diff.scope_added, "Should detect scope addition"
    added = diff.scope_added["acorns"]
    assert "api.acorns.com" in added
    assert "staging.acorns.com" in added
    assert "acorns.com" not in added, "Existing domain shouldn't be in 'added'"
    assert not diff.scope_removed
    print(f"PASS: scope added — {sorted(added)}")


def test_diff_scope_removed():
    """Verify a scope removal triggers a 'scope removed' alert."""
    prev_state = {
        "programs": {
            "acorns": {
                "name": "Acorns Grow",
                "url": "https://bugcrowd.com/acorns",
                "domains": ["acorns.com", "old.acorns.com"],
            }
        }
    }
    current = [
        Program(slug="acorns", name="Acorns Grow", url="https://bugcrowd.com/acorns",
                domains=["acorns.com"], platform="bugcrowd"),
    ]
    diff, _ = diff_programs(current, prev_state)
    assert not diff.new_programs
    assert not diff.scope_added
    assert "acorns" in diff.scope_removed
    removed = diff.scope_removed["acorns"]
    assert "old.acorns.com" in removed
    print(f"PASS: scope removed — {sorted(removed)}")


def test_diff_no_change():
    """Verify no diff when state is unchanged."""
    prev_state = {
        "programs": {
            "acorns": {
                "name": "Acorns Grow",
                "url": "https://bugcrowd.com/acorns",
                "domains": ["acorns.com"],
            }
        }
    }
    current = [
        Program(slug="acorns", name="Acorns Grow", url="https://bugcrowd.com/acorns",
                domains=["acorns.com"], platform="bugcrowd"),
    ]
    diff, _ = diff_programs(current, prev_state)
    assert not diff.has_changes(), "Should detect no changes"
    print("PASS: no-change case")


def test_diff_case_insensitive():
    """Verify domain comparison is case-insensitive (some sources mix cases)."""
    prev_state = {
        "programs": {
            "x": {"name": "X", "url": "https://bugcrowd.com/x", "domains": ["Acorns.COM"]},
        }
    }
    current = [
        Program(slug="x", name="X", url="https://bugcrowd.com/x",
                domains=["acorns.com"], platform="bugcrowd"),
    ]
    diff, _ = diff_programs(current, prev_state)
    assert not diff.has_changes(), "Case-only difference should not trigger alert"
    print("PASS: case-insensitive domain comparison")


if __name__ == "__main__":
    tests = [
        test_slug_extraction,
        test_real_fetch,
        test_diff_new_program,
        test_diff_scope_added,
        test_diff_scope_removed,
        test_diff_no_change,
        test_diff_case_insensitive,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"FAIL: {t.__name__} — {e}")
            failed += 1
    print()
    if failed:
        print(f"{failed}/{len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"All {len(tests)} tests passed — bot is ready to deploy")
