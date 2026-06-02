import json

from repo_review.advisories import (
    Advisory,
    AdvisoryDataset,
    default_dataset,
    load_advisory_dataset,
)


def test_load_parses_version_and_advisories_from_snapshot_json(tmp_path):
    path = tmp_path / "advisories.json"
    path.write_text(json.dumps({
        "dataset_version": "2026-05-01",
        "advisories": [
            {
                "ecosystem": "npm",
                "package": "lodash",
                "affected": ["4.17.20", "4.17.19"],
                "cve": "CVE-2021-23337",
                "cvss": 7.2,
            },
        ],
    }))

    dataset = load_advisory_dataset(path)

    assert dataset.version == "2026-05-01"
    assert dataset.advisories == (
        Advisory("npm", "lodash", ("4.17.20", "4.17.19"), "CVE-2021-23337", 7.2),
    )


def test_default_dataset_loads_the_bundled_snapshot(tmp_path):
    dataset = default_dataset()

    # The bundled snapshot is stamped and non-empty so runs are reproducible.
    assert isinstance(dataset, AdvisoryDataset)
    assert dataset.version
    assert len(dataset.advisories) > 0
    # Spans both ecosystems the check parses.
    ecosystems = {a.ecosystem for a in dataset.advisories}
    assert {"npm", "maven"} <= ecosystems
