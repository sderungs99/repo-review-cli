import json

from repo_review.manifest import load_manifest


def test_loads_every_subject_repo_pinned_to_its_sha(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "repos": [
                    {"name": "auth-service", "source": "/srv/auth", "sha": "a" * 40},
                    {"name": "payments-service", "source": "/srv/pay", "sha": "b" * 40},
                ]
            }
        )
    )

    entries = load_manifest(manifest)

    assert [e.name for e in entries] == ["auth-service", "payments-service"]
    assert entries[0].source == "/srv/auth"
    assert entries[0].sha == "a" * 40
