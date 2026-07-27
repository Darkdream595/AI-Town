"""
魔法环境交互（DOC-MAGIC-009）

- REQ-MAGIC-017：12 个 handler 封闭注册表，strict 参数子 Schema
- REQ-MAGIC-018：只能经目标 owner 公开接口改动世界，禁止直写他域
- RULE-MAGIC-051：持续实例必须声明时限，到期清理
- RULE-MAGIC-052：结算与 SpellCastCommitted 同一事务原子成败
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..foundation import generate_ulid
from .constants import (
    ANCHOR_MAX_DURATION_GAME_MINUTES,
    ANCHOR_SCENE_CAP,
    EFFECT_MAX_DURATION_GAME_MINUTES,
    HEAL_DAILY_CAP_BPS,
    SCENE_EFFECT_INSTANCE_CAP,
    EffectInstanceState,
)


class EffectError(Exception):
    """效果结算失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: REQ-MAGIC-017：首版恰好 12 个 handler
EFFECT_IDS = (
    "magic.effect.ignite",
    "magic.effect.extinguish",
    "magic.effect.heal_minor",
    "magic.effect.cure_illness",
    "magic.effect.purify_anomaly",
    "magic.effect.reinforce_structure",
    "magic.effect.place_ley_anchor",
    "magic.effect.detect_magic",
    "magic.effect.conjure_light",
    "magic.effect.veil_illusion",
    "magic.effect.soothe_spirit",
    "magic.effect.curse_weariness",
)

#: 每个 handler 的 strict 参数子 Schema（未知键拒绝）
EFFECT_PARAM_FIELDS: Dict[str, frozenset] = {
    "magic.effect.ignite": frozenset({"ignite_strength"}),
    "magic.effect.extinguish": frozenset(),
    "magic.effect.heal_minor": frozenset({"heal_base", "skill_scale_per_25_rating"}),
    "magic.effect.cure_illness": frozenset(),
    "magic.effect.purify_anomaly": frozenset({"purify_progress"}),
    "magic.effect.reinforce_structure": frozenset({"decay_reduction_bps", "duration_game_minutes"}),
    "magic.effect.place_ley_anchor": frozenset({"radius_wu", "ley_anchor_bonus_q1000", "duration_game_minutes"}),
    "magic.effect.detect_magic": frozenset(),
    "magic.effect.conjure_light": frozenset({"light_radius_wu", "duration_game_minutes"}),
    "magic.effect.veil_illusion": frozenset({"veil_radius_wu", "duration_game_minutes"}),
    "magic.effect.soothe_spirit": frozenset({"soothe_strength"}),
    "magic.effect.curse_weariness": frozenset({"duration_game_minutes"}),
}

#: RULE-MAGIC-036：效果类别决定 declared_purpose 合法集
EFFECT_PURPOSE_WHITELIST: Dict[str, frozenset] = {
    "magic.effect.ignite": frozenset({"utility", "combat"}),
    "magic.effect.extinguish": frozenset({"utility", "defense"}),
    "magic.effect.heal_minor": frozenset({"healing"}),
    "magic.effect.cure_illness": frozenset({"healing"}),
    "magic.effect.purify_anomaly": frozenset({"utility", "ritual"}),
    "magic.effect.reinforce_structure": frozenset({"utility", "ritual"}),
    "magic.effect.place_ley_anchor": frozenset({"ritual", "utility"}),
    "magic.effect.detect_magic": frozenset({"utility"}),
    "magic.effect.conjure_light": frozenset({"utility"}),
    "magic.effect.veil_illusion": frozenset({"utility", "combat", "defense"}),
    "magic.effect.soothe_spirit": frozenset({"healing", "utility", "ritual"}),
    "magic.effect.curse_weariness": frozenset({"combat", "ritual"}),
}

#: 有害效果（法律判定的攻击性输入）
HARMFUL_EFFECTS = frozenset({"magic.effect.ignite", "magic.effect.curse_weariness"})
#: 救助方向效果（RULE-MAGIC-025 紧急例外适用）
RESCUE_EFFECTS = frozenset({"magic.effect.heal_minor", "magic.effect.cure_illness", "magic.effect.purify_anomaly"})


@dataclass
class WorldMagicEffectInstance:
    """DES-MAGIC-009 §5.2 的持续效果实例"""

    effect_instance_id: str
    effect_id: str
    caster_id: str
    scene_id: str
    position: Optional[Dict]
    radius_wu: float
    detectable: bool
    expires_at_game_time: int
    source_event_id: str
    state: EffectInstanceState = EffectInstanceState.ACTIVE
    instance_revision: int = 0
    effect_schema_version: int = 1


class EffectInstanceStore:
    """MAGIC 拥有的持续实例聚合；到期/驱散/上限"""

    def __init__(self) -> None:
        self._instances: Dict[str, WorldMagicEffectInstance] = {}

    def create(
        self,
        effect_id: str,
        caster_id: str,
        scene_id: str,
        position: Optional[Dict],
        radius_wu: float,
        duration_game_minutes: int,
        game_time: int,
        source_event_id: str,
        detectable: bool = True,
    ) -> WorldMagicEffectInstance:
        is_anchor = effect_id == "magic.effect.place_ley_anchor"
        cap = ANCHOR_MAX_DURATION_GAME_MINUTES if is_anchor else EFFECT_MAX_DURATION_GAME_MINUTES
        if not (1 <= duration_game_minutes <= cap):
            raise EffectError("magic_effect_duration_invalid", f"{duration_game_minutes} > {cap}")
        active_in_scene = [
            i for i in self._instances.values()
            if i.scene_id == scene_id and i.state is EffectInstanceState.ACTIVE
        ]
        if len(active_in_scene) >= SCENE_EFFECT_INSTANCE_CAP:
            raise EffectError("magic_effect_instance_cap", scene_id)
        if is_anchor:
            anchors = [i for i in active_in_scene if i.effect_id == effect_id]
            if len(anchors) >= ANCHOR_SCENE_CAP:
                raise EffectError("magic_ley_anchor_cap", scene_id)
            for anchor in anchors:
                if position is not None and anchor.position is not None:
                    distance = _distance(position, anchor.position)
                    if distance < radius_wu + anchor.radius_wu:
                        # 锚点重叠拒绝，ley 加成不叠加
                        raise EffectError("magic_ley_anchor_overlap", anchor.effect_instance_id)
        instance = WorldMagicEffectInstance(
            effect_instance_id=generate_ulid(),
            effect_id=effect_id,
            caster_id=caster_id,
            scene_id=scene_id,
            position=position,
            radius_wu=radius_wu,
            detectable=detectable,
            expires_at_game_time=game_time + duration_game_minutes,
            source_event_id=source_event_id,
        )
        self._instances[instance.effect_instance_id] = instance
        return instance

    def get(self, effect_instance_id: str) -> WorldMagicEffectInstance:
        instance = self._instances.get(effect_instance_id)
        if instance is None:
            raise EffectError("magic_effect_instance_unknown", effect_instance_id)
        return instance

    def dispel(self, effect_instance_id: str) -> WorldMagicEffectInstance:
        instance = self.get(effect_instance_id)
        if instance.state is not EffectInstanceState.ACTIVE:
            raise EffectError("magic_effect_instance_terminal", instance.state.value)
        instance.state = EffectInstanceState.DISPELLED
        instance.instance_revision += 1
        return instance

    def expire_overdue(self, game_time: int) -> List[str]:
        """TIME 到期队列驱动；0× 暂停不调用即不过期"""
        expired = []
        for instance in self._instances.values():
            if instance.state is EffectInstanceState.ACTIVE and game_time > instance.expires_at_game_time:
                instance.state = EffectInstanceState.EXPIRED
                instance.instance_revision += 1
                expired.append(instance.effect_instance_id)
        return expired

    def ley_anchor_bonus_q1000(self, scene_id: str, position: Dict, game_time: int) -> int:
        """RULE-MAGIC-011 的 ley 修正 overlay；读取侧按到期时间判定，超期即失效"""
        for instance in self._instances.values():
            if (
                instance.effect_id == "magic.effect.place_ley_anchor"
                and instance.scene_id == scene_id
                and instance.state is EffectInstanceState.ACTIVE
                and game_time <= instance.expires_at_game_time
                and instance.position is not None
                and _distance(position, instance.position) <= instance.radius_wu
            ):
                return 100
        return 0

    def detectable_facts(self, scene_id: str, center: Dict, radius_wu: float, game_time: int) -> List[Dict]:
        """RULE-MAGIC-048：只揭示 detectable 标记的结构化事实"""
        facts = []
        for instance in self._instances.values():
            if (
                instance.scene_id == scene_id
                and instance.state is EffectInstanceState.ACTIVE
                and game_time <= instance.expires_at_game_time
                and instance.detectable
                and instance.position is not None
                and _distance(center, instance.position) <= radius_wu
            ):
                facts.append({
                    "fact_kind": "world_magic_effect",
                    "effect_id": instance.effect_id,
                    "radius_wu": instance.radius_wu,
                })
        return facts


def _distance(a: Dict, b: Dict) -> float:
    return ((a["x_wu"] - b["x_wu"]) ** 2 + (a["y_wu"] - b["y_wu"]) ** 2) ** 0.5


class HealDailyLedger:
    """RULE-MAGIC-065：治疗日累计上限分账记账（MAGIC 侧）"""

    def __init__(self) -> None:
        self._daily: Dict[Tuple[str, int], int] = {}

    def cap_for(hp_max: int) -> int:
        return hp_max * HEAL_DAILY_CAP_BPS // 10000

    def record(self, target_id: str, game_day: int, amount: int) -> int:
        key = (target_id, game_day)
        self._daily[key] = self._daily.get(key, 0) + amount
        return self._daily[key]

    def total(self, target_id: str, game_day: int) -> int:
        return self._daily.get((target_id, game_day), 0)


@dataclass
class EffectContext:
    """Handler 的结算输入：Catalog 参数 + 世界状态 + owner 端口"""

    caster_id: str
    caster_school_rating: int
    scene_id: str
    game_time: int
    game_day: int
    source_event_id: str
    target_refs: List[str]
    aim_point: Optional[Dict]
    caster_position: Dict
    instance_store: EffectInstanceStore
    heal_ledger: HealDailyLedger
    event_port: object  # EVENT owner 接口（火源/异常/建筑/灵体）
    resident_port: object  # RESIDENT owner 接口（HealthEffectCommand/病程）
    memory_port: object  # MEMORY owner 接口（观察输入）
    land_permission: Callable[[str, Dict], bool] = lambda _c, _p: True
    magical_item_detector: Callable[[str, Dict, float], List[Dict]] = lambda _s, _c, _r: []


def _validate_params(effect_id: str, parameters: Dict) -> None:
    allowed = EFFECT_PARAM_FIELDS[effect_id]
    extra = set(parameters) - allowed
    if extra:
        raise EffectError("magic_effect_params_invalid", f"{effect_id} extra: {sorted(extra)}")
    missing = allowed - set(parameters)
    if missing:
        raise EffectError("magic_effect_params_invalid", f"{effect_id} missing: {sorted(missing)}")


def check_effect_preconditions(effect_id: str, parameters: Dict, ctx: EffectContext) -> None:
    """RULE-MAGIC-052：两阶段第一阶段——全部前置通过才进入应用"""
    _validate_params(effect_id, parameters)
    if effect_id == "magic.effect.ignite":
        state = ctx.event_port.flammable_state(ctx.aim_point)
        if not state["registered"]:
            raise EffectError("magic_ignite_unregistered", "not a registered flammable point")
        if state["active"]:
            raise EffectError("magic_ignite_occupied", "fire source already active")
        if state["wet"]:
            raise EffectError("magic_ignite_wet", "flammable point is wet")
    elif effect_id == "magic.effect.extinguish":
        state = ctx.event_port.flammable_state(ctx.aim_point)
        if not state["registered"] or not state["active"]:
            raise EffectError("magic_extinguish_inactive", "no active fire source")
    elif effect_id == "magic.effect.heal_minor":
        hp_current, hp_max = ctx.resident_port.hp_state(ctx.target_refs[0])
        if hp_current >= hp_max:
            # allow_overheal=false：满血目标整次施法拒绝
            raise EffectError("magic_heal_overheal_forbidden", ctx.target_refs[0])
    elif effect_id == "magic.effect.place_ley_anchor":
        if not ctx.land_permission(ctx.caster_id, ctx.aim_point):
            raise EffectError("magic_ley_anchor_permission_denied", ctx.caster_id)


def apply_effect(effect_id: str, parameters: Dict, ctx: EffectContext) -> Dict:
    """两阶段第二阶段：路由 owner 应用或创建持续实例"""
    if effect_id == "magic.effect.ignite":
        ctx.event_port.ignite(ctx.aim_point, ctx.source_event_id)
        return {"routed": "EVENT", "kind": "FireSourceIgnited"}
    if effect_id == "magic.effect.extinguish":
        ctx.event_port.extinguish(ctx.aim_point, ctx.source_event_id)
        return {"routed": "EVENT", "kind": "FireSourceExtinguished"}
    if effect_id == "magic.effect.heal_minor":
        target = ctx.target_refs[0]
        heal = parameters["heal_base"] + (ctx.caster_school_rating // 25) * parameters["skill_scale_per_25_rating"]
        _hp_current, hp_max = ctx.resident_port.hp_state(target)
        spent = ctx.heal_ledger.total(target, ctx.game_day)
        cap = HealDailyLedger.cap_for(hp_max)
        applied = max(0, min(heal, cap - spent))  # REQ-MAGIC-023：超出日上限部分结算为 0
        if applied > 0:
            ctx.resident_port.apply_health_effect(target, applied, ctx.source_event_id)
            ctx.heal_ledger.record(target, ctx.game_day, applied)
        return {"routed": "RESIDENT", "kind": "HealthEffectCommand", "hp_delta": applied}
    if effect_id == "magic.effect.cure_illness":
        ctx.resident_port.cure_illness(ctx.target_refs[0], ctx.source_event_id)
        return {"routed": "RESIDENT", "kind": "IllnessCured"}
    if effect_id == "magic.effect.curse_weariness":
        # RULE-MAGIC-047：登记为病程实例，必须带退出条件，无永久诅咒
        ctx.resident_port.apply_illness(
            ctx.target_refs[0], "illness.arcane_weariness",
            parameters["duration_game_minutes"], ctx.source_event_id,
        )
        return {"routed": "RESIDENT", "kind": "IllnessApplied", "illness_id": "illness.arcane_weariness"}
    if effect_id == "magic.effect.purify_anomaly":
        ctx.event_port.purify_anomaly(ctx.aim_point, parameters["purify_progress"], ctx.source_event_id)
        return {"routed": "EVENT", "kind": "AnomalyPurified"}
    if effect_id == "magic.effect.reinforce_structure":
        ctx.event_port.reinforce_structure(
            ctx.target_refs[0], parameters["decay_reduction_bps"],
            parameters["duration_game_minutes"], ctx.source_event_id,
        )
        return {"routed": "EVENT", "kind": "StructureReinforced"}
    if effect_id == "magic.effect.place_ley_anchor":
        instance = ctx.instance_store.create(
            effect_id, ctx.caster_id, ctx.scene_id, ctx.aim_point,
            parameters["radius_wu"], parameters["duration_game_minutes"],
            ctx.game_time, ctx.source_event_id,
        )
        return {"routed": "MAGIC", "kind": "LeyAnchorPlaced", "effect_instance_id": instance.effect_instance_id}
    if effect_id == "magic.effect.detect_magic":
        facts = ctx.instance_store.detectable_facts(
            ctx.scene_id, ctx.caster_position, 64.0, ctx.game_time
        )
        facts.extend(ctx.magical_item_detector(ctx.scene_id, ctx.caster_position, 64.0))
        ctx.memory_port.record_observation(ctx.caster_id, facts, ctx.source_event_id)
        return {"routed": "MEMORY", "kind": "MagicDetected", "fact_count": len(facts)}
    if effect_id == "magic.effect.conjure_light":
        instance = ctx.instance_store.create(
            effect_id, ctx.caster_id, ctx.scene_id, ctx.caster_position,
            parameters["light_radius_wu"], parameters["duration_game_minutes"],
            ctx.game_time, ctx.source_event_id,
        )
        return {"routed": "MAGIC", "kind": "LightConjured", "effect_instance_id": instance.effect_instance_id}
    if effect_id == "magic.effect.veil_illusion":
        instance = ctx.instance_store.create(
            effect_id, ctx.caster_id, ctx.scene_id, ctx.aim_point,
            parameters["veil_radius_wu"], parameters["duration_game_minutes"],
            ctx.game_time, ctx.source_event_id,
        )
        return {"routed": "MAGIC", "kind": "VeilConjured", "effect_instance_id": instance.effect_instance_id}
    if effect_id == "magic.effect.soothe_spirit":
        ctx.event_port.soothe_spirit(ctx.target_refs[0], ctx.source_event_id)
        return {"routed": "EVENT", "kind": "SpiritSoothed"}
    raise EffectError("magic_effect_unknown", effect_id)


def run_effect_bindings(bindings: Tuple[Dict, ...], ctx: EffectContext) -> List[Dict]:
    """RULE-MAGIC-052：按数组顺序结算；任一前置失败整次拒绝，无半效果"""
    for binding in bindings:
        effect_id = binding["effect_id"]
        if effect_id not in EFFECT_PARAM_FIELDS:
            raise EffectError("magic_effect_unknown", effect_id)
        check_effect_preconditions(effect_id, binding["parameters"], ctx)
    results = []
    for binding in bindings:
        results.append(apply_effect(binding["effect_id"], binding["parameters"], ctx))
    return results
