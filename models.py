"""
Dataclasses for program tracking.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Program:
    """A single Bugcrowd program."""
    slug: str           # unique key (e.g. "acme-corp")
    name: str
    url: str            # program page URL
    domains: List[str]  # in-scope assets
    platform: str       # always "bugcrowd" for us

    def domain_signature(self) -> frozenset:
        """Stable signature for change detection."""
        return frozenset(d.lower().strip() for d in self.domains if d.strip())


@dataclass
class ProgramDiff:
    """Difference between previous and current state."""
    new_programs: List[Program] = field(default_factory=list)
    scope_added: dict = field(default_factory=dict)   # {slug: [domains]}
    scope_removed: dict = field(default_factory=dict)  # {slug: [domains]}

    def has_changes(self) -> bool:
        return bool(self.new_programs or self.scope_added or self.scope_removed)
