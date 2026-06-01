import subprocess

import pytest

from repo_review.acquire import acquire_repo
from repo_review.manifest import ManifestEntry


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _make_source_repo(path):
    """A real git repo with two commits; returns the FIRST commit's SHA."""
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "README.md").write_text("# v1 of the readme with plenty of words here\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "first")
    first_sha = _git(path, "rev-parse", "HEAD")
    (path / "README.md").write_text("# v2 changed later\n")
    _git(path, "commit", "-qam", "second")
    return first_sha


def test_acquire_checks_out_exactly_the_pinned_sha(tmp_path):
    source = tmp_path / "source"
    pinned_sha = _make_source_repo(source)
    entry = ManifestEntry(name="auth-service", source=str(source), sha=pinned_sha)

    checkout = acquire_repo(entry, tmp_path / "work")

    assert _git(checkout, "rev-parse", "HEAD") == pinned_sha
    # The working tree reflects the pinned commit, not the later one.
    assert "v1 of the readme" in (checkout / "README.md").read_text()


def test_acquire_expands_a_tilde_in_the_source_path(tmp_path, monkeypatch):
    # A manifest may store sources as ~/... ; git can't expand ~, the tool must.
    monkeypatch.setenv("HOME", str(tmp_path))
    source = tmp_path / "code" / "auth-service"
    source.parent.mkdir(parents=True)
    pinned_sha = _make_source_repo(source)
    entry = ManifestEntry(
        name="auth-service", source="~/code/auth-service", sha=pinned_sha
    )

    checkout = acquire_repo(entry, tmp_path / "work")

    assert _git(checkout, "rev-parse", "HEAD") == pinned_sha


def test_acquire_failure_reports_the_repo_and_source(tmp_path):
    entry = ManifestEntry(
        name="missing-service", source=str(tmp_path / "nope"), sha="0" * 40
    )

    with pytest.raises(RuntimeError) as exc:
        acquire_repo(entry, tmp_path / "work")

    assert "missing-service" in str(exc.value)
    assert str(tmp_path / "nope") in str(exc.value)
