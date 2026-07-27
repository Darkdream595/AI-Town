"""
施法合法性（DOC-MAGIC-005）

- REQ-MAGIC-009：固定七级校验顺序，任一级失败即短路
- REQ-MAGIC-010：世界合法性为确定性函数，模型文本不参与判定
- RULE-MAGIC-022..025：prohibited 无提交后受罚路径；restricted 需证据；紧急例外只限救助方向
- RULE-MAGIC-026/028：提交携带幂等键，提交时在最新 Revision 重验全部七级
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from ..foundation import generate_ulid
from .constants import (
    Legality,
    VerdictClassification,
)
from .effects import (
    EFFECT_PARAM_FIELDS,
    EFFECT_PURPOSE_WHITELIST,
    HARMFUL_EFFECTS,
    RESCUE_EFFECTS,
    EffectContext,
    EffectError,
    EffectInstanceStore,
    HealDailyLedger,
    apply_effect,
    check_effect_preconditions,
    run_effect_bindings,
)
from .learning import LearningRegistry
from .mana import CasterRegistry, ManaError
from .schools import SchoolRegistry
from .spells import SpellCatalog, SpellDefinition, SpellError, validate_target_arguments


class CastingError(Exception):
    """施法校验/提交失败；code 复用 DES-MAGIC-005 reason 集"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class SpellCastCommand:
    """DES-MAGIC-005 归一化命令；authorization 只携带 event ID"""

    command_id: str
    world_id: str
    expected_revision: int
    caster_id: str
    spell_id: str
    scene_id: str
    game_time: int
    game_day: int
    target_refs: Tuple[str, ...] = ()
    aim_point: Optional[Dict] = None
    declared_purpose: str = "utility"
    authorization_event_ids: Tuple[str, ...] = ()
    caster_position: Dict = field(default_factory=lambda: {"x_wu": 0.0, "y_wu": 0.0})


@dataclass(frozen=True)
class CastVerdict:
    classification: VerdictClassification
    legality: Optional[Legality] = None
    failed_stage: Optional[int] = None
    reason_code: Optional[str] = None


@dataclass
class SpellCastCommitted:
    """施法成功的原子提交记录"""

    cast_event_id: str
    command_id: str
    caster_id: str
    spell_id: str
    school_id: str
    legality: Legality
    effect_results: Tuple[Dict, ...]
    committed_revision: int
    game_time: int


#: reason_code → 校验分级（RULE-MAGIC-027）
_CLASSIFICATION_BY_REASON = {
    "MAGIC_SPELL_UNKNOWN": VerdictClassification.FORBIDDEN,
    "MAGIC_SPELL_NOT_LEARNED": VerdictClassification.FORBIDDEN,
    "MAGIC_LEGALITY_PROHIBITED": VerdictClassification.FORBIDDEN,
    "MAGIC_CASTER_EXHAUSTED": VerdictClassification.REPLAN_REQUIRED,
    "MAGIC_MANA_INSUFFICIENT": VerdictClassification.REPLAN_REQUIRED,
    "MAGIC_TARGET_INVALID": VerdictClassification.REPLAN_REQUIRED,
    "MAGIC_RANGE_EXCEEDED": VerdictClassification.REPLAN_REQUIRED,
    "MAGIC_PREREQUISITE_MISSING": VerdictClassification.REPLAN_REQUIRED,
    "MAGIC_CONSENT_MISSING": VerdictClassification.REPLAN_REQUIRED,
    "MAGIC_ENCOUNTER_RULE_CONFLICT": VerdictClassification.REPLAN_REQUIRED,
    "stale_revision": VerdictClassification.REPLAN_REQUIRED,
}


class CastingEngine:
    """七级校验与原子提交的唯一授权点（RULE-MAGIC-035）"""

    def __init__(
        self,
        catalog: SpellCatalog,
        schools: SchoolRegistry,
        mana_registry: CasterRegistry,
        learning: LearningRegistry,
        instance_store: EffectInstanceStore,
        heal_ledger: HealDailyLedger,
        event_port: object,
        resident_port: object,
        memory_port: object,
        target_resolver: Callable[[str], Optional[Dict]],
        skill_rating: Callable[[str, str], int],
        ability_provider: Callable[[str], Set[str]],
        item_tag_provider: Callable[[str], Set[str]],
        jurisdiction_of: Callable[[str], str],
        encounter_of: Callable[[str], Optional[Dict]],
        land_permission: Optional[Callable[[str, Dict], bool]] = None,
        magical_item_detector: Optional[Callable[[str, Dict, float], List[Dict]]] = None,
    ) -> None:
        self._catalog = catalog
        self._schools = schools
        self._mana = mana_registry
        self._learning = learning
        self._instance_store = instance_store
        self._heal_ledger = heal_ledger
        self._event_port = event_port
        self._resident_port = resident_port
        self._memory_port = memory_port
        self._target_resolver = target_resolver
        self._skill_rating = skill_rating
        self._abilities = ability_provider
        self._item_tags = item_tag_provider
        self._jurisdiction_of = jurisdiction_of
        self._encounter_of = encounter_of
        self._land_permission = land_permission or (lambda _c, _p: True)
        self._magical_item_detector = magical_item_detector or (lambda _s, _c, _r: [])
        self._revision = 0
        self._committed: Dict[str, SpellCastCommitted] = {}
        self._by_command: Dict[str, object] = {}
        self._rituals: Dict[str, Dict] = {}

    @property
    def revision(self) -> int:
        return self._revision

    def committed_cast(self, command_id: str) -> Optional[SpellCastCommitted]:
        result = self._by_command.get(command_id)
        return result if isinstance(result, SpellCastCommitted) else None

    # -- 七级校验 --

    def validate_spell_cast(self, command: SpellCastCommand) -> CastVerdict:
        """REQ-MAGIC-009：固定顺序短路；REQ-MAGIC-010：判定确定性"""
        try:
            legality = self._run_stages(command)
        except CastingError as exc:
            return CastVerdict(
                classification=_CLASSIFICATION_BY_REASON.get(
                    exc.code, VerdictClassification.REPLAN_REQUIRED
                ),
                failed_stage=getattr(exc, "stage", None),
                reason_code=exc.code,
            )
        return CastVerdict(classification=VerdictClassification.VALID, legality=legality)

    def _fail(self, stage: int, code: str, message: str = "") -> None:
        error = CastingError(code, message)
        error.stage = stage  # type: ignore[attr-defined]
        raise error

    def _run_stages(self, command: SpellCastCommand) -> Legality:
        # 第 1 级：Schema/引用解析
        spell = self._catalog._spells.get(command.spell_id)
        if spell is None:
            self._fail(1, "MAGIC_SPELL_UNKNOWN", command.spell_id)
        try:
            validate_target_arguments(spell, list(command.target_refs), command.aim_point)
        except SpellError:
            self._fail(1, "MAGIC_TARGET_INVALID", command.spell_id)
        for binding in spell.effect_bindings:
            allowed = EFFECT_PURPOSE_WHITELIST.get(binding["effect_id"], frozenset())
            if command.declared_purpose not in allowed:
                # RULE-MAGIC-036：用途伪装按 REPLAN 退回
                self._fail(1, "MAGIC_TARGET_INVALID", f"purpose {command.declared_purpose}")
        # 第 2 级：SpellKnowledge 已学
        if not self._learning.is_learned(command.caster_id, command.spell_id):
            self._fail(2, "MAGIC_SPELL_NOT_LEARNED", command.spell_id)
        # 第 3 级：枯竭与 Mana 充足（冷却由候选投影过滤，非提交校验级）
        try:
            self._mana.check_castable(command.caster_id, spell.mana_cost)
        except ManaError as exc:
            self._fail(3, exc.code, command.caster_id)
        # 第 4 级：目标模式与射程（同 Scene、欧氏距离）
        self._check_targets(command, spell)
        # 第 5 级：结构化前置
        self._check_prerequisites(command, spell)
        # 第 6 级：世界合法性（确定性函数）
        legality = self._check_world_legality(command, spell)
        # 第 7 级：Reservation 与最新 Revision 提交检查
        if command.expected_revision != self._revision:
            self._fail(
                7, "stale_revision",
                f"expected {command.expected_revision}, at {self._revision}",
            )
        return legality

    def _check_targets(self, command: SpellCastCommand, spell: SpellDefinition) -> None:
        if spell.target_mode.value in ("self", "none", "area_around_caster"):
            return
        if spell.target_mode.value == "ground_point":
            aim = command.aim_point
            if aim is None or "x_wu" not in aim or "y_wu" not in aim:
                self._fail(4, "MAGIC_TARGET_INVALID", "aim_point must be valid world point")
            if _distance(command.caster_position, aim) > spell.range_wu:
                self._fail(4, "MAGIC_RANGE_EXCEEDED", command.spell_id)
            return
        for target_id in command.target_refs:
            target = self._target_resolver(target_id)
            if target is None:
                self._fail(4, "MAGIC_TARGET_INVALID", target_id)
            if target["scene_id"] != command.scene_id:
                # RULE-MAGIC-016：跨 Scene 目标一律非法
                self._fail(4, "MAGIC_TARGET_INVALID", f"cross-scene {target_id}")
            if _distance(command.caster_position, target["position"]) > spell.range_wu:
                self._fail(4, "MAGIC_RANGE_EXCEEDED", target_id)

    def _check_prerequisites(self, command: SpellCastCommand, spell: SpellDefinition) -> None:
        prerequisites = spell.prerequisites
        rating = self._skill_rating(command.caster_id, spell.school_id)
        if rating < prerequisites["min_school_skill_rating"]:
            self._fail(5, "MAGIC_PREREQUISITE_MISSING", "min_school_skill_rating")
        abilities = self._abilities(command.caster_id)
        if not set(prerequisites["required_ability_ids"]) <= abilities:
            self._fail(5, "MAGIC_PREREQUISITE_MISSING", "required_ability_ids")
        for required_spell in prerequisites["required_spell_ids"]:
            if not self._learning.is_learned(command.caster_id, required_spell):
                self._fail(5, "MAGIC_PREREQUISITE_MISSING", required_spell)
        if not set(prerequisites["required_item_tags"]) <= self._item_tags(command.caster_id):
            self._fail(5, "MAGIC_PREREQUISITE_MISSING", "required_item_tags")

    def _check_world_legality(self, command: SpellCastCommand, spell: SpellDefinition) -> Legality:
        """REQ-MAGIC-010：同输入同输出；模型自由文本不参与"""
        school = self._schools.get(spell.school_id)
        effective = (
            spell.legal_override.value
            if spell.legal_override.value != "inherit"
            else school.default_legal_baseline
        )
        if effective == "prohibited":
            self._fail(6, "MAGIC_LEGALITY_PROHIBITED", spell.spell_id)
        harmful = any(b["effect_id"] in HARMFUL_EFFECTS for b in spell.effect_bindings)
        jurisdiction = self._jurisdiction_of(command.scene_id)
        if (
            harmful
            and spell.school_id in ("school.elemental", "school.spirit")
            and jurisdiction == "town_public"
        ):
            # RULE-MAGIC-022/034：镇区公共空间攻击性法术一律拒绝，
            # 不存在提交后受罚路径，也不因发起战斗追溯合法化
            self._fail(6, "MAGIC_LEGALITY_PROHIBITED", spell.spell_id)
        encounter = self._encounter_of(command.caster_id)
        in_combat_with_targets = bool(
            encounter
            and command.target_refs
            and all(t in encounter.get("enemies", ()) for t in command.target_refs)
        )
        if harmful and encounter is not None and not in_combat_with_targets:
            self._fail(6, "MAGIC_ENCOUNTER_RULE_CONFLICT", spell.spell_id)
        # 同意与授权
        targets_others = any(t != command.caster_id for t in command.target_refs)
        if spell.consent_required and targets_others:
            if command.authorization_event_ids:
                pass  # 结构化证据满足
            elif self._emergency_exception_applies(command, spell):
                pass  # RULE-MAGIC-025：救助方向紧急例外，强制记录
            else:
                self._fail(6, "MAGIC_CONSENT_MISSING", spell.spell_id)
        if effective == "restricted":
            if not command.authorization_event_ids and not self._emergency_exception_applies(command, spell):
                self._fail(6, "MAGIC_CONSENT_MISSING", spell.spell_id)
            return Legality.RESTRICTED_AUTHORIZED
        return Legality.PERMITTED

    def _emergency_exception_applies(self, command: SpellCastCommand, spell: SpellDefinition) -> bool:
        """RULE-MAGIC-025：无行为能力目标的救助方向紧急例外；伤害方向不存在"""
        if not all(b["effect_id"] in RESCUE_EFFECTS for b in spell.effect_bindings):
            return False
        for target_id in command.target_refs:
            if target_id == command.caster_id:
                continue
            target = self._target_resolver(target_id)
            if target is None or not target.get("incapacitated", False):
                return False
        return bool(command.target_refs)

    def build_effect_context(
        self,
        command: SpellCastCommand,
        spell: SpellDefinition,
        source_event_id: str,
    ) -> EffectContext:
        """结算上下文统一装配点；法器与本体施法共用同一组 owner 端口"""
        return EffectContext(
            caster_id=command.caster_id,
            caster_school_rating=self._skill_rating(command.caster_id, spell.school_id),
            scene_id=command.scene_id,
            game_time=command.game_time,
            game_day=command.game_day,
            source_event_id=source_event_id,
            target_refs=list(command.target_refs),
            aim_point=command.aim_point,
            caster_position=command.caster_position,
            instance_store=self._instance_store,
            heal_ledger=self._heal_ledger,
            event_port=self._event_port,
            resident_port=self._resident_port,
            memory_port=self._memory_port,
            land_permission=self._land_permission,
            magical_item_detector=self._magical_item_detector,
        )

    # -- 提交 --

    def commit_spell_cast(self, command: SpellCastCommand) -> SpellCastCommitted:
        """RULE-MAGIC-026/028：幂等；提交时最新 Revision 重验全部七级"""
        if command.command_id in self._by_command:
            result = self._by_command[command.command_id]
            if isinstance(result, CastingError):
                raise result
            return result  # type: ignore[return-value]
        verdict = self.validate_spell_cast(command)
        if verdict.classification is not VerdictClassification.VALID:
            error = CastingError(verdict.reason_code or "MAGIC_TARGET_INVALID")
            self._by_command[command.command_id] = error
            raise error
        spell = self._catalog.get(command.spell_id)
        cast_event_id = generate_ulid()
        caster_state = self._mana.get(command.caster_id)
        # 消耗与效果结算同一事务：先效果前置（run 内部两阶段），再扣 Mana
        ctx = self.build_effect_context(command, spell, cast_event_id)
        try:
            results = run_effect_bindings(spell.effect_bindings, ctx)
            self._mana.consume_mana(
                cast_event_id, command.caster_id, spell.mana_cost,
                caster_state.state_revision,
            )
        except (EffectError, ManaError) as exc:
            error = CastingError(getattr(exc, "code", "magic_effect_unknown"))
            self._by_command[command.command_id] = error
            raise error
        if spell.cooldown_game_minutes > 0:
            self._mana.set_cooldown(
                command.caster_id, spell.spell_id,
                command.game_time + spell.cooldown_game_minutes,
            )
        self._revision += 1
        committed = SpellCastCommitted(
            cast_event_id=cast_event_id,
            command_id=command.command_id,
            caster_id=command.caster_id,
            spell_id=spell.spell_id,
            school_id=spell.school_id,
            legality=verdict.legality or Legality.PERMITTED,
            effect_results=tuple(results),
            committed_revision=self._revision,
            game_time=command.game_time,
        )
        self._committed[cast_event_id] = committed
        self._by_command[command.command_id] = committed
        # RULE-MAGIC-033：成功施法授予学派 XP（幂等）
        self._learning.grant_cast_xp(command.caster_id, spell.school_id, cast_event_id)
        return committed

    # -- 法器施放（RULE-MAGIC-054） --

    def validate_item_cast(self, command: SpellCastCommand, spell: SpellDefinition) -> Legality:
        """法器保留第 4、6、7 级；跳过学习、Mana 与技能门槛"""
        self._check_targets(command, spell)
        legality = self._check_world_legality(command, spell)
        if command.expected_revision != self._revision:
            self._fail(
                7, "stale_revision",
                f"expected {command.expected_revision}, at {self._revision}",
            )
        return legality

    def commit_item_cast(
        self,
        command: SpellCastCommand,
        spell: SpellDefinition,
        charge_hook: Callable[[str], None],
    ) -> SpellCastCommitted:
        """REQ-MAGIC-020：充能扣减与效果事件原子结算；不设冷却、不授 XP（物品代劳）"""
        if command.command_id in self._by_command:
            result = self._by_command[command.command_id]
            if isinstance(result, CastingError):
                raise result
            return result  # type: ignore[return-value]
        cast_event_id = generate_ulid()
        try:
            legality = self.validate_item_cast(command, spell)
            ctx = self.build_effect_context(command, spell, cast_event_id)
            for binding in spell.effect_bindings:
                effect_id = binding["effect_id"]
                if effect_id not in EFFECT_PARAM_FIELDS:
                    raise EffectError("magic_effect_unknown", effect_id)
                check_effect_preconditions(effect_id, binding["parameters"], ctx)
            # 前置全部通过才扣充能，保证同 (item, event) 最多扣一次且不落半效果
            charge_hook(cast_event_id)
            results = [
                apply_effect(binding["effect_id"], binding["parameters"], ctx)
                for binding in spell.effect_bindings
            ]
        except CastingError as exc:
            self._by_command[command.command_id] = exc
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code is None:
                raise
            error = CastingError(code)
            self._by_command[command.command_id] = error
            raise error
        self._revision += 1
        committed = SpellCastCommitted(
            cast_event_id=cast_event_id,
            command_id=command.command_id,
            caster_id=command.caster_id,
            spell_id=spell.spell_id,
            school_id=spell.school_id,
            legality=legality,
            effect_results=tuple(results),
            committed_revision=self._revision,
            game_time=command.game_time,
        )
        self._committed[cast_event_id] = committed
        self._by_command[command.command_id] = committed
        return committed

    # -- ritual（RULE-MAGIC-026） --

    def begin_ritual(self, command: SpellCastCommand) -> Dict:
        """ritual 先建立长行动；第 1..6 级先行，提交级在检查点重验"""
        verdict_stages = CastVerdict(VerdictClassification.VALID)
        try:
            spell = self._catalog._spells.get(command.spell_id)
            if spell is None:
                self._fail(1, "MAGIC_SPELL_UNKNOWN", command.spell_id)
            validate_target_arguments(spell, list(command.target_refs), command.aim_point)
            if not self._learning.is_learned(command.caster_id, command.spell_id):
                self._fail(2, "MAGIC_SPELL_NOT_LEARNED", command.spell_id)
            self._check_targets(command, spell)
            self._check_prerequisites(command, spell)
            self._check_world_legality(command, spell)
        except CastingError:
            raise
        ritual = {
            "command": command,
            "spell": spell,
            "completed_work_units": 0,
            "state": "in_progress",
        }
        self._rituals[command.command_id] = ritual
        return ritual

    def ritual_checkpoint(self, command_id: str, game_time: int, game_day: int) -> str:
        """检查点按 RULE-MAGIC-026 重验第 3、4、6 级；失败转 interrupted"""
        ritual = self._rituals.get(command_id)
        if ritual is None or ritual["state"] != "in_progress":
            raise CastingError("magic_ritual_unknown", command_id)
        command: SpellCastCommand = ritual["command"]
        spell: SpellDefinition = ritual["spell"]
        command = SpellCastCommand(
            **{**command.__dict__, "game_time": game_time, "game_day": game_day}
        )
        try:
            self._mana.check_castable(command.caster_id, spell.mana_cost)
            self._check_targets(command, spell)
            self._check_world_legality(command, spell)
        except CastingError:
            ritual["state"] = "interrupted"
            raise
        ritual["completed_work_units"] += 1
        if ritual["completed_work_units"] >= (spell.required_work_units or 1):
            ritual["state"] = "completed"
            self.commit_spell_cast(
                SpellCastCommand(
                    **{**command.__dict__, "expected_revision": self._revision}
                )
            )
        return ritual["state"]


def _distance(a: Dict, b: Dict) -> float:
    return ((a["x_wu"] - b["x_wu"]) ** 2 + (a["y_wu"] - b["y_wu"]) ** 2) ** 0.5
