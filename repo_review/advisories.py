"""The pinned vulnerability dataset the dependency-CVE check matches against.

v1 runs purely on a local snapshot (ADR-0007): a versioned JSON file bundled
with the tool, never a live lookup. The snapshot is generated out-of-band from
an upstream source (OSV) and committed; every review reads it with no network,
so a run is reproducible and defensible from (checkouts + dataset version).
"""

import json
from dataclasses import dataclass
from pathlib import Path

# The committed snapshot, generated out-of-band from OSV and pinned (ADR-0007).
_BUNDLED_SNAPSHOT = Path(__file__).parent / "data" / "advisories.json"


@dataclass(frozen=True)
class Advisory:
    """One known-vulnerable (ecosystem, package) at an exact set of versions."""

    ecosystem: str
    package: str
    affected: tuple[str, ...]
    cve: str
    cvss: float


@dataclass(frozen=True)
class AdvisoryDataset:
    """A pinned snapshot of advisories, stamped with its ``version``."""

    version: str
    advisories: tuple[Advisory, ...]

    def matches(self, ecosystem: str, package: str, version: str) -> list[Advisory]:
        """Advisories whose affected set contains this exact (package, version)."""
        return [
            advisory
            for advisory in self.advisories
            if advisory.ecosystem == ecosystem
            and advisory.package == package
            and version in advisory.affected
        ]


def load_advisory_dataset(path: Path) -> AdvisoryDataset:
    """Parse a pinned advisory snapshot JSON into an AdvisoryDataset."""
    data = json.loads(Path(path).read_text())
    advisories = tuple(
        Advisory(
            ecosystem=entry["ecosystem"],
            package=entry["package"],
            affected=tuple(entry["affected"]),
            cve=entry["cve"],
            cvss=entry["cvss"],
        )
        for entry in data["advisories"]
    )
    return AdvisoryDataset(version=data["dataset_version"], advisories=advisories)


def default_dataset() -> AdvisoryDataset:
    """Load the snapshot bundled with the tool."""
    return load_advisory_dataset(_BUNDLED_SNAPSHOT)
