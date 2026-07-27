"""
TEST-PLAYER-029..032：镇长治理权限、预算与信息边界（DOC-PLAYER-008）

- TEST-PLAYER-029：Mayor command union、office 与 jurisdiction
- TEST-PLAYER-030：budget/appropriation/encumbrance 并发守恒
- TEST-PLAYER-031：secret/private inference 与 direct mutation 拒绝
- TEST-PLAYER-032：office revocation、public-work Saga 与幂等恢复
"""

import pytest

from src.player import (
    MAYOR_COMMAND_TYPES,
    MayorCommand,
    MayorCommandError,
    MayorCommandValidator,
    MayorOffice,
    PlayerMode,
    PublicBudgetState,
)

WORLD = "01K1WRDX000000000000000001"
OFFICE_ID = "01K1FFCE000000000000000001"
HOLDER = "01K1RSDT000000000000000001"


def _command(command_type="mayor.public_work.propose", command_id="cmd-1", **payload_overrides):
    payloads = {
        "mayor.public_work.propose": {
            "office_id": OFFICE_ID,
            "expected_office_version": 4,
            "jurisdiction_id": "jurisdiction.crowncreek",
            "public_subject_id": "road.market.east",
            "purpose_id": "public_work.road_repair",
            "maximum_budget_copper_feather": 5000,
            "requested_completion_game_time": 10080,
        },
        "mayor.budget.propose": {
            "office_id": OFFICE_ID,
            "expected_office_version": 4,
            "jurisdiction_id": "jurisdiction.crowncreek",
            "purpose_id": "budget.festival",
            "maximum_budget_copper_feather": 3000,
        },
        "mayor.emergency.respond": {
            "office_id": OFFICE_ID,
            "expected_office_version": 4,
            "jurisdiction_id": "jurisdiction.crowncreek",
            "emergency_policy_id": "emergency.fire_response",
            "reason_code": "emergency.market_fire",
            "expires_game_time": 20000,
            "maximum_budget_copper_feather": 8000,
        },
        "mayor.notice.publish": {
            "office_id": OFFICE_ID,
            "expected_office_version": 4,
            "jurisdiction_id": "jurisdiction.crowncreek",
            "content_id": "notice.harvest_festival",
        },
    }
    payload = payloads[command_type]
    payload.update(payload_overrides)
    return MayorCommand(
        command_id=command_id,
        world_id=WORLD,
        expected_revision=312,
        type=command_type,
        payload=payload,
    )


def _office(active=True, version=4, jurisdictions=("jurisdiction.crowncreek",)):
    return MayorOffice(
        office_id=OFFICE_ID,
        holder_resident_id=HOLDER,
        jurisdiction_ids=set(jurisdictions),
        version=version,
        active=active,
    )


def _budget(balance=10000, limit=5000):
    return PublicBudgetState(
        balance_copper_feather=balance,
        appropriation_limit_copper_feather=limit,
    )


class TestUnionAndAuthority:
    """TEST-PLAYER-029"""

    def test_registered_union_complete(self):
        assert MAYOR_COMMAND_TYPES == frozenset({
            "mayor.budget.propose", "mayor.tax.propose", "mayor.wage.propose",
            "mayor.public_work.propose", "mayor.notice.publish",
            "mayor.festival.schedule", "mayor.emergency.respond",
            "mayor.statistics.query",
        })

    def test_strict_payload_schema(self):
        with pytest.raises(MayorCommandError) as exc:
            _command("mayor.notice.publish", extra_field="x")
        assert exc.value.code == "MAYOR_PAYLOAD_SCHEMA_MISMATCH"

    def test_unregistered_type_rejected(self):
        with pytest.raises(MayorCommandError) as exc:
            MayorCommand(
                command_id="c", world_id=WORLD, expected_revision=1,
                type="mayor.declare_martial_law", payload={},
            )
        assert exc.value.code == "MAYOR_COMMAND_TYPE_UNREGISTERED"

    def test_requires_mayor_active_mode(self):
        validator = MayorCommandValidator()
        with pytest.raises(MayorCommandError) as exc:
            validator.validate(
                _command(), PlayerMode.RESIDENT_ACTIVE, _office(), authority_version=4,
                budget=_budget(),
            )
        assert exc.value.code == "MAYOR_MODE_REQUIRED"

    def test_requires_active_office(self):
        validator = MayorCommandValidator()
        with pytest.raises(MayorCommandError) as exc:
            validator.validate(
                _command(), PlayerMode.MAYOR_ACTIVE, _office(active=False),
                authority_version=4, budget=_budget(),
            )
        assert exc.value.code == "MAYOR_OFFICE_INACTIVE"

    def test_jurisdiction_must_match(self):
        validator = MayorCommandValidator()
        with pytest.raises(MayorCommandError) as exc:
            validator.validate(
                _command(), PlayerMode.MAYOR_ACTIVE,
                _office(jurisdictions=("jurisdiction.other",)),
                authority_version=4, budget=_budget(),
            )
        assert exc.value.code == "MAYOR_JURISDICTION_MISMATCH"

    def test_office_version_must_match(self):
        validator = MayorCommandValidator()
        with pytest.raises(MayorCommandError) as exc:
            validator.validate(
                _command(expected_office_version=3), PlayerMode.MAYOR_ACTIVE,
                _office(version=4), authority_version=4, budget=_budget(),
            )
        assert exc.value.code == "MAYOR_OFFICE_VERSION_STALE"

    def test_valid_command_produces_audit_record(self):
        validator = MayorCommandValidator()
        record = validator.validate(
            _command(), PlayerMode.MAYOR_ACTIVE, _office(), authority_version=4,
            budget=_budget(),
        )
        assert record.result == "proposed"
        assert record.office_id == OFFICE_ID
        # §9：拒绝也产生审计
        with pytest.raises(MayorCommandError):
            validator.validate(
                _command(command_id="cmd-2"), PlayerMode.RESIDENT_ACTIVE,
                _office(), authority_version=4, budget=_budget(),
            )
        assert [r.result for r in validator.audit_records] == ["proposed", "denied"]


class TestBudgetTripleConstraint:
    """TEST-PLAYER-030"""

    def test_two_competing_appropriations_at_most_one_succeeds(self):
        validator = MayorCommandValidator()
        budget = _budget(balance=10000, limit=5000)
        validator.validate(
            _command("mayor.budget.propose", command_id="cmd-1"),
            PlayerMode.MAYOR_ACTIVE, _office(), 4, budget,
        )
        # 第二笔 3000 超出剩余 appropriation（5000-3000=2000）
        with pytest.raises(MayorCommandError) as exc:
            validator.validate(
                _command("mayor.public_work.propose", command_id="cmd-2"),
                PlayerMode.MAYOR_ACTIVE, _office(), 4, budget,
            )
        assert exc.value.code == "MAYOR_BUDGET_EXCEEDS_APPROPRIATION"
        assert budget.encumbered_copper_feather == 3000

    def test_balance_insufficient_rejected(self):
        budget = _budget(balance=100, limit=5000)
        with pytest.raises(MayorCommandError) as exc:
            budget.try_encumber("enc-1", 500)
        assert exc.value.code == "MAYOR_BUDGET_INSUFFICIENT_BALANCE"

    def test_no_negative_balance_or_mint(self):
        budget = _budget(balance=1000, limit=5000)
        budget.try_encumber("enc-1", 1000)
        budget.settle_encumbrance("enc-1")
        assert budget.balance_copper_feather == 0
        with pytest.raises(MayorCommandError):
            budget.try_encumber("enc-2", 1)

    def test_saga_failure_releases_encumbrance(self):
        """§8：Saga 失败释放 active Encumbrance，无部分支出"""
        budget = _budget()
        budget.try_encumber("enc-1", 4000)
        released = budget.release_encumbrance("enc-1")
        assert released == 4000
        assert budget.encumbered_copper_feather == 0
        assert budget.balance_copper_feather == 10000

    def test_emergency_policy_constraints(self):
        """RULE-PLAYER-040：注册 policy + 上限 + 期限 + reason"""
        validator = MayorCommandValidator()
        with pytest.raises(MayorCommandError) as exc:
            validator.validate(
                _command("mayor.emergency.respond",
                         emergency_policy_id="emergency.purge_dissidents"),
                PlayerMode.MAYOR_ACTIVE, _office(), 4, _budget(),
            )
        assert exc.value.code == "MAYOR_EMERGENCY_POLICY_UNREGISTERED"

        with pytest.raises(MayorCommandError) as exc:
            validator.validate(
                _command("mayor.emergency.respond", maximum_budget_copper_feather=99999),
                PlayerMode.MAYOR_ACTIVE, _office(), 4, _budget(balance=200000, limit=200000),
            )
        assert exc.value.code == "MAYOR_EMERGENCY_CAP_EXCEEDED"


class TestPrivacyAndDirectMutation:
    """TEST-PLAYER-031"""

    @pytest.mark.parametrize(
        "action",
        ["set_affection", "confiscate_property", "force_combat_outcome",
         "set_building_stage", "edit_collision", "forge_world_event",
         "mint_currency", "set_balance"],
    )
    def test_mayor_forbidden_actions_rejected(self, action):
        with pytest.raises(MayorCommandError) as exc:
            MayorCommandValidator.assert_mayor_cannot(action)
        assert exc.value.code == "MAYOR_DIRECT_MUTATION_REJECTED"

    @pytest.mark.parametrize(
        "field",
        ["private_memory", "personal_secret", "shared_secret",
         "private_inventory", "relationship_raw", "undisclosed_health"],
    )
    def test_public_projection_rejects_private_fields(self, field):
        with pytest.raises(MayorCommandError) as exc:
            MayorCommandValidator.filter_public_projection({field: "x", "population": 12})
        assert exc.value.code == "MAYOR_PUBLIC_PROJECTION_DISCLOSURE_VIOLATION"

    def test_public_projection_allows_aggregates(self):
        fields = MayorCommandValidator.filter_public_projection(
            {"population": 12, "treasury_total": 10000}
        )
        assert fields["population"] == 12


class TestRevocationAndIdempotency:
    """TEST-PLAYER-032"""

    def test_idempotent_replay_same_command(self):
        validator = MayorCommandValidator()
        budget = _budget()
        first = validator.validate(
            _command("mayor.notice.publish", command_id="cmd-1"),
            PlayerMode.MAYOR_ACTIVE, _office(), 4, budget,
        )
        second = validator.validate(
            _command("mayor.notice.publish", command_id="cmd-1"),
            PlayerMode.MAYOR_ACTIVE, _office(), 4, budget,
        )
        # §7：相同幂等 key 相同 payload 返回原 decision
        assert second.record_id == first.record_id

    def test_budget_replay_does_not_double_encumber(self):
        validator = MayorCommandValidator()
        budget = _budget(balance=10000, limit=5000)
        validator.validate(
            _command("mayor.budget.propose", command_id="cmd-1"),
            PlayerMode.MAYOR_ACTIVE, _office(), 4, budget,
        )
        validator.validate(
            _command("mayor.budget.propose", command_id="cmd-1"),
            PlayerMode.MAYOR_ACTIVE, _office(), 4, budget,
        )
        # 重放不重复占用 Encumbrance
        assert budget.encumbered_copper_feather == 3000

    def test_same_command_id_different_payload_conflicts(self):
        validator = MayorCommandValidator()
        validator.validate(
            _command("mayor.notice.publish", command_id="cmd-1"),
            PlayerMode.MAYOR_ACTIVE, _office(), 4, _budget(),
        )
        with pytest.raises(MayorCommandError) as exc:
            validator.validate(
                _command("mayor.notice.publish", command_id="cmd-1",
                         content_id="notice.other"),
                PlayerMode.MAYOR_ACTIVE, _office(), 4, _budget(),
            )
        assert exc.value.code == "MAYOR_COMMAND_ID_CONFLICT"

    def test_revoked_office_blocks_new_commands(self):
        """§7：权限撤销阻止新命令"""
        validator = MayorCommandValidator()
        validator.validate(
            _command("mayor.notice.publish", command_id="cmd-1"),
            PlayerMode.MAYOR_ACTIVE, _office(), 4, _budget(),
        )
        with pytest.raises(MayorCommandError) as exc:
            validator.validate(
                _command("mayor.notice.publish", command_id="cmd-2"),
                PlayerMode.MAYOR_ACTIVE, _office(active=False), 4, _budget(),
            )
        assert exc.value.code == "MAYOR_OFFICE_INACTIVE"
