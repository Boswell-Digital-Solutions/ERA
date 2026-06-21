import json
from pathlib import Path

from era_integrations.centipede_export import validate_centipede_export_bundle
from scripts.generate_self_healing_proof_fixture import (
    FIXTURE_PATH,
    FIXTURE_RUN_ID,
    build_fixture_bundle,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_committed_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_committed_fixture_exists_and_is_centipede_intake():
    bundle = _load_committed_fixture()
    assert bundle["schema_version"] == "centipede.intake.v1"
    assert bundle["source_system"] == "era"


def test_committed_fixture_passes_export_validation():
    bundle = _load_committed_fixture()
    result = validate_centipede_export_bundle(bundle)
    assert result["ok"], result["errors"]


def test_committed_fixture_has_exactly_one_self_healing_projection():
    bundle = _load_committed_fixture()
    projections = bundle["self_healing_projections"]
    assert len(projections) == 1
    assert bundle["registry_projections"] == []

    projection = projections[0]
    assert projection["finding_class"] == "accuracy_gate_failed"
    assert projection["operator_review_required"] is True
    assert projection["blocked_reason"] is None
    # Every run-scoped id embeds the placeholder run id so a consumer can swap a
    # fresh run id in to avoid already-consumed collisions.
    assert FIXTURE_RUN_ID in projection["projection_id"]
    assert FIXTURE_RUN_ID in projection["evidence_bundle_id"]


def test_committed_fixture_is_clearly_synthetic():
    bundle = _load_committed_fixture()
    evidence = bundle["evidence_bundles"][0]
    repro = evidence["reproduction_contract"]
    assert "synthetic" in json.dumps(bundle).lower()
    assert repro["command_id"] == "era_self_healing_proof_gate"


def test_committed_fixture_matches_regeneration():
    # The committed file must equal a fresh deterministic regeneration so the
    # fixture cannot silently drift away from the live bundle shape.
    regenerated = build_fixture_bundle()
    committed = _load_committed_fixture()
    assert committed == regenerated
