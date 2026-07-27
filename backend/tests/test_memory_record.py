"""
测试 MemoryRecordV1 strict Schema 与写入幂等

覆盖 TEST-MEMORY-001..008（DOC-MEMORY-001/002 §11）
"""

import copy

import pytest

from src.memory import (
    Eligibility,
    MemorySchemaError,
    MemoryWriteCandidate,
    WriteKeyConflictError,
    WriteKeyStore,
    canonical_candidate_hash,
    compute_write_key,
    evaluate_write_eligibility,
    memory_metadata_projection,
    validate_memory_record,
)

WORLD_ID = "01K1AB2CD3EF4GH5JK6MNP7QR0"
OWNER_ID = "01K1AB2CD3EF4GH5JK6MNP7QRS"
MEMORY_ID = "01K1AB2CD3EF4GH5JK6MNP7QRT"
POLICY_ID = "01K1AB2CD3EF4GH5JK6MNP7QRW"
EVENT_ID = "01K1AB2CD3EF4GH5JK6MNP7QRV"


def _base_record(kind: str, payload: dict) -> dict:
    return {
        "schema_version": 1,
        "memory_id": MEMORY_ID,
        "world_id": WORLD_ID,
        "memory_owner_id": OWNER_ID,
        "memory_kind": kind,
        "state": "active",
        "created_at_revision": 10,
        "created_at_game_time": 1830,
        "last_reactivated_game_time": None,
        "importance_q1000": 500,
        "confidence_q1000": 800,
        "subject_refs": [OWNER_ID],
        "semantic_tags": ["topic.market.gossip"],
        "provenance": {
            "source_kind": "domain_event",
            "source_event_ids": [EVENT_ID],
            "origin_actor_id": None,
            "direct_observer_id": OWNER_ID,
            "derived_from_memory_ids": [],
            "transform_rule_ids": [],
            "source_revision": 9,
        },
        "access_policy_id": POLICY_ID,
        "payload": payload,
        "record_version": 1,
    }


def _episodic_payload() -> dict:
    return {
        "kind": "episodic_memory",
        "representation": "direct_episode",
        "summary_text": "在市场上看到交易",
        "participant_ids": [OWNER_ID],
        "location_ids": ["semantic_area.crown_creek.market"],
        "emotion_id": "calm",
        "emotion_intensity_q1000": 300,
        "source_memory_ids": [],
    }


def _belief_payload() -> dict:
    return {
        "kind": "semantic_belief",
        "claim": {
            "predicate_id": "shop.apothecary.is_open",
            "subject_ref": "building.crown_creek.apothecary",
            "object_value": True,
        },
        "evidence_memory_ids": [],
        "contradiction_memory_ids": [],
    }


def _impression_payload() -> dict:
    return {
        "kind": "social_impression",
        "target_resident_id": OWNER_ID,
        "trait_id": "trait.social.friendly",
        "valence_q1000": 400,
        "evidence_memory_ids": [],
    }


def _commitment_payload() -> dict:
    return {
        "kind": "commitment",
        "commitment_id": EVENT_ID,
        "promisor_id": OWNER_ID,
        "beneficiary_ids": [WORLD_ID],
        "terms_id": "terms.trade.deliver_herbs",
        "deadline_game_time": 2880,
        "status": "accepted",
    }


def _routine_payload() -> dict:
    return {
        "kind": "routine_knowledge",
        "procedure_id": "procedure.craft.healing_potion",
        "step_action_ids": ["step.gather.herb"],
        "proficiency_q1000": 700,
        "last_success_event_id": None,
    }


class TestFiveKindSchema:
    """TEST-MEMORY-001：五类 strict Schema、discriminator 与 additionalProperties"""

    @pytest.mark.parametrize(
        "kind,payload",
        [
            ("episodic_memory", _episodic_payload()),
            ("semantic_belief", _belief_payload()),
            ("social_impression", _impression_payload()),
            ("commitment", _commitment_payload()),
            ("routine_knowledge", _routine_payload()),
        ],
    )
    def test_valid_records(self, kind, payload):
        record = _base_record(kind, payload)
        assert validate_memory_record(record) is record

    def test_kind_mismatch_rejected(self):
        record = _base_record("semantic_belief", _episodic_payload())
        with pytest.raises(MemorySchemaError):
            validate_memory_record(record)

    def test_extra_field_rejected(self):
        record = _base_record("episodic_memory", _episodic_payload())
        record["rogue_field"] = 1
        with pytest.raises(MemorySchemaError):
            validate_memory_record(record)

    def test_unknown_kind_rejected(self):
        record = _base_record("dream_memory", _episodic_payload())
        with pytest.raises(MemorySchemaError):
            validate_memory_record(record)

    def test_belief_truth_field_forbidden(self):
        # RULE-MEMORY-005：SemanticBelief 不含 is_true/objective_truth
        payload = _belief_payload()
        payload["claim"]["is_true"] = True
        record = _base_record("semantic_belief", payload)
        with pytest.raises(MemorySchemaError):
            validate_memory_record(record)


class TestProvenanceInvariants:
    """TEST-MEMORY-002：provenance/world/revision 不变量"""

    def test_missing_provenance_source_rejected(self):
        record = _base_record("episodic_memory", _episodic_payload())
        record["provenance"]["source_event_ids"] = []
        with pytest.raises(MemorySchemaError):
            validate_memory_record(record)

    def test_source_revision_after_creation_rejected(self):
        record = _base_record("episodic_memory", _episodic_payload())
        record["provenance"]["source_revision"] = 99
        with pytest.raises(MemorySchemaError):
            validate_memory_record(record)


class TestMetadataBoundary:
    """TEST-MEMORY-003：metadata/materialize 数据边界"""

    def test_metadata_has_no_payload(self):
        record = _base_record("episodic_memory", _episodic_payload())
        metadata = memory_metadata_projection(record)
        assert "payload" not in metadata
        assert "summary_text" not in str(metadata)
        assert "provenance" not in metadata


class TestTombstoneAndRoundTrip:
    """TEST-MEMORY-004：tombstone 与 round-trip"""

    def test_tombstoned_payload_must_be_null(self):
        record = _base_record("episodic_memory", _episodic_payload())
        record["state"] = "tombstoned"
        with pytest.raises(MemorySchemaError):
            validate_memory_record(record)
        record["payload"] = None
        assert validate_memory_record(record) is record

    def test_round_trip_equal(self):
        import json

        record = _base_record("semantic_belief", _belief_payload())
        reloaded = json.loads(json.dumps(record, ensure_ascii=False))
        assert validate_memory_record(reloaded) == record


def _candidate(**overrides) -> MemoryWriteCandidate:
    defaults = dict(
        candidate_id=MEMORY_ID,
        world_id=WORLD_ID,
        memory_owner_id=OWNER_ID,
        memory_kind="episodic_memory",
        source_kind="domain_event",
        source_event_ids=(EVENT_ID,),
        source_memory_ids=(),
        observed_revision=10,
        observed_game_time=1830,
        observation_evidence=None,
    )
    defaults.update(overrides)
    return MemoryWriteCandidate(**defaults)


class TestWriteEligibility:
    """TEST-MEMORY-005/007：source eligibility 正反例、观察证据"""

    def test_committed_event_eligible(self):
        result = evaluate_write_eligibility(_candidate(), frozenset({EVENT_ID}))
        assert result.eligibility == Eligibility.ELIGIBLE

    def test_uncommitted_event_rejected(self):
        result = evaluate_write_eligibility(_candidate(), frozenset())
        assert result.eligibility == Eligibility.REJECTED
        assert result.reason_code == "MEMORY_SOURCE_NOT_COMMITTED"

    def test_direct_observation_requires_evidence(self):
        candidate = _candidate(source_kind="direct_observation", observation_evidence=None)
        result = evaluate_write_eligibility(candidate, frozenset({EVENT_ID}))
        assert result.eligibility == Eligibility.REJECTED
        assert result.reason_code == "MEMORY_OBSERVATION_UNPROVEN"

    def test_direct_observation_with_evidence(self):
        evidence = {
            "observer_id": OWNER_ID,
            "scene_id": "region.crown_creek_town",
            "sense_modes": ["sight"],
            "evidence_hash": "a" * 64,
        }
        candidate = _candidate(source_kind="direct_observation", observation_evidence=evidence)
        result = evaluate_write_eligibility(candidate, frozenset({EVENT_ID}))
        assert result.eligibility == Eligibility.ELIGIBLE

    def test_unresolvable_policy_deferred(self):
        result = evaluate_write_eligibility(
            _candidate(), frozenset({EVENT_ID}), access_policy_resolvable=False
        )
        assert result.eligibility == Eligibility.DEFERRED
        assert result.reason_code == "MEMORY_ACCESS_POLICY_UNRESOLVED"

    def test_no_source_rejected(self):
        candidate = _candidate(source_event_ids=(), source_memory_ids=())
        result = evaluate_write_eligibility(candidate, frozenset())
        assert result.eligibility == Eligibility.REJECTED


class TestWriteKeyIdempotency:
    """TEST-MEMORY-006/008：write-key 固定向量与幂等冲突"""

    def test_write_key_fixed_vector(self):
        candidate = _candidate()
        canonical = (
            WORLD_ID
            + "\n"
            + OWNER_ID
            + "\nepisodic_memory\ndomain_event\n"
            + EVENT_ID
            + "\n\nmemory-write/v1"
        )
        import hashlib

        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert compute_write_key(candidate) == expected

    def test_replay_returns_original(self):
        store = WriteKeyStore()
        candidate = _candidate()
        write_key = compute_write_key(candidate)
        candidate_hash = canonical_candidate_hash(candidate)
        first = store.commit(WORLD_ID, write_key, candidate_hash, "mem-1", "evt-1")
        replayed = store.commit(WORLD_ID, write_key, candidate_hash, "mem-2", "evt-2")
        assert replayed.memory_id == "mem-1"
        assert store.replay(WORLD_ID, write_key).event_id == "evt-1"

    def test_conflict_raises(self):
        store = WriteKeyStore()
        candidate = _candidate()
        write_key = compute_write_key(candidate)
        store.commit(WORLD_ID, write_key, canonical_candidate_hash(candidate), "mem-1", "evt-1")
        with pytest.raises(WriteKeyConflictError):
            store.commit(WORLD_ID, write_key, "different-hash", "mem-2", "evt-2")
