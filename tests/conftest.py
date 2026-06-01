import json
import subprocess

import pytest


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def make_git_repo(tmp_path):
    """Factory: create a local git repo with one commit; return (path, sha)."""
    counter = {"n": 0}

    def _make(name, readme_text):
        counter["n"] += 1
        path = tmp_path / "sources" / name
        path.mkdir(parents=True)
        _git(path, "init", "-q")
        _git(path, "config", "user.email", "t@example.com")
        _git(path, "config", "user.name", "Test")
        if readme_text is not None:
            (path / "README.md").write_text(readme_text)
        else:
            (path / "main.py").write_text("print('hello')\n")
        _git(path, "add", "-A")
        _git(path, "commit", "-q", "-m", "initial")
        return path, _git(path, "rev-parse", "HEAD")

    return _make


@pytest.fixture
def write_manifest(tmp_path):
    """Factory: write a manifest JSON from (name, source, sha) entries."""

    def _write(entries):
        path = tmp_path / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "repos": [
                        {"name": n, "source": str(s), "sha": sha}
                        for (n, s, sha) in entries
                    ]
                }
            )
        )
        return path

    return _write
