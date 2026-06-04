"""Repo acquisition: clone a Subject Repo and check it out at its pinned SHA.

In v1 acquisition is the *only* git interaction (ADR-0007): everything
downstream operates on the resulting local checkout, with no network at
analysis time. The pinned SHA (ADR-0001) is what makes the run reproducible.
"""

import os
import subprocess
from pathlib import Path

from repo_review.manifest import ManifestEntry


def acquire_repo(entry: ManifestEntry, workdir: Path) -> Path:
    """Clone ``entry`` into ``workdir`` and check out its pinned SHA.

    When ``entry.sha`` is ``None`` the clone is left on the default branch at
    its latest commit, so the review tracks the live repository instead of a
    reproducible snapshot (ADR-0001).

    Returns the path to the local checkout. A leading ``~`` in the Manifest
    source is expanded here — git does not expand it, and the shell never sees
    it because the source comes from the Manifest JSON, not the command line.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    checkout = workdir / entry.name
    source = os.path.expanduser(entry.source)

    _git(entry, ["clone", "--quiet", source, str(checkout)])
    if entry.sha is not None:
        _git(entry, ["checkout", "--quiet", entry.sha], cwd=checkout)
    return checkout


def _git(entry: ManifestEntry, args: list[str], cwd: Path | None = None) -> None:
    """Run a git command, raising a diagnosable error if it fails."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to acquire Subject Repo '{entry.name}' "
            f"(source: {entry.source}, sha: {entry.sha}): "
            f"git {' '.join(args)} exited {result.returncode}\n"
            f"{result.stderr.strip()}"
        )
