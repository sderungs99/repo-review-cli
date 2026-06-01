"""The Manifest: the frozen, SHA-pinned definition of what was reviewed.

The checked-in input file listing every Subject Repo pinned to an exact commit
SHA (ADR-0001). It is the source of the review's reproducibility — drift is
never silent because updating the review means deliberately bumping a SHA here.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ManifestEntry:
    name: str
    source: str
    sha: str


def load_manifest(path: Path) -> list[ManifestEntry]:
    """Load every Subject Repo entry from the Manifest file."""
    data = json.loads(Path(path).read_text())
    return [
        ManifestEntry(name=r["name"], source=r["source"], sha=r["sha"])
        for r in data["repos"]
    ]
