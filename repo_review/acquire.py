"""Repo acquisition: clone a Subject Repo and check it out at its pinned SHA.

In v1 acquisition is the *only* git interaction (ADR-0007): everything
downstream operates on the resulting local checkout, with no network at
analysis time. The pinned SHA (ADR-0001) is what makes the run reproducible.
"""

import subprocess
from pathlib import Path

from repo_review.manifest import ManifestEntry


def acquire_repo(entry: ManifestEntry, workdir: Path) -> Path:
    """Clone ``entry`` into ``workdir`` and check out its pinned SHA.

    Returns the path to the local checkout.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    checkout = workdir / entry.name

    subprocess.run(
        ["git", "clone", "--quiet", entry.source, str(checkout)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "--quiet", entry.sha],
        cwd=checkout,
        check=True,
        capture_output=True,
    )
    return checkout
