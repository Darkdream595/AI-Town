"""MAGIC 测试共享夹具：recording 端口与 CastingEngine 工厂"""

from types import SimpleNamespace
from typing import Dict, Optional, Tuple

from src.magic import (
    CasterRegistry,
    CastingEngine,
    DailyCastBudget,
    EffectInstanceStore,
    HealDailyLedger,
    LearningRegistry,
    SchoolRegistry,
    SpellCastCommand,
    build_default_schools,
    build_default_spell_catalog,
)


class RecordingEventPort:
    """EVENT owner 假端口：记录调用并可配置火源状态"""

    def __init__(self) -> None:
        self.calls = []
        self.flammable: Dict[Tuple[float, float], Dict] = {}

    def register_flammable(self, x: float, y: float, *, registered=True, active=False, wet=False) -> None:
        self.flammable[(x, y)] = {"registered": registered, "active": active, "wet": wet}

    def flammable_state(self, aim_point: Optional[Dict]) -> Dict:
        if aim_point is None:
            return {"registered": False, "active": False, "wet": False}
        return self.flammable.get(
            (aim_point["x_wu"], aim_point["y_wu"]),
            {"registered": False, "active": False, "wet": False},
        )

    def ignite(self, aim_point, source_event_id) -> None:
        self.calls.append(("ignite", aim_point, source_event_id))
        state = self.flammable[(aim_point["x_wu"], aim_point["y_wu"])]
        state["active"] = True

    def extinguish(self, aim_point, source_event_id) -> None:
        self.calls.append(("extinguish", aim_point, source_event_id))
        state = self.flammable[(aim_point["x_wu"], aim_point["y_wu"])]
        state["active"] = False

    def purify_anomaly(self, aim_point, progress, source_event_id) -> None:
        self.calls.append(("purify_anomaly", aim_point, progress, source_event_id))

    def reinforce_structure(self, target_id, decay_reduction_bps, duration, source_event_id) -> None:
        self.calls.append(("reinforce_structure", target_id, decay_reduction_bps, duration, source_event_id))

    def soothe_spirit(self, target_id, source_event_id) -> None:
        self.calls.append(("soothe_spirit", target_id, source_event_id))


class RecordingResidentPort:
    """RESIDENT owner 假端口：HP 与病程"""

    def __init__(self) -> None:
        self.hp: Dict[str, list] = {}
        self.illnesses = []
        self.calls = []

    def set_hp(self, resident_id: str, current: int, maximum: int) -> None:
        self.hp[resident_id] = [current, maximum]

    def hp_state(self, resident_id: str):
        current, maximum = self.hp.get(resident_id, [50, 100])
        return current, maximum

    def apply_health_effect(self, resident_id: str, amount: int, source_event_id) -> None:
        self.calls.append(("apply_health_effect", resident_id, amount, source_event_id))
        current, maximum = self.hp[resident_id]
        self.hp[resident_id] = [min(maximum, current + amount), maximum]

    def cure_illness(self, resident_id: str, source_event_id) -> None:
        self.calls.append(("cure_illness", resident_id, source_event_id))

    def apply_illness(self, resident_id: str, illness_id: str, duration: int, source_event_id) -> None:
        self.calls.append(("apply_illness", resident_id, illness_id, duration, source_event_id))
        self.illnesses.append((resident_id, illness_id, duration))


class RecordingMemoryPort:
    """MEMORY owner 假端口：观察输入"""

    def __init__(self) -> None:
        self.observations = []

    def record_observation(self, caster_id: str, facts, source_event_id) -> None:
        self.observations.append((caster_id, list(facts), source_event_id))


def make_engine(
    *,
    ratings: Optional[Dict[Tuple[str, str], int]] = None,
    targets: Optional[Dict[str, Dict]] = None,
    jurisdiction: str = "wilderness",
    encounters: Optional[Dict[str, Dict]] = None,
    abilities: Optional[Dict[str, set]] = None,
    item_tags: Optional[Dict[str, set]] = None,
    land_permission=None,
    magical_item_detector=None,
) -> SimpleNamespace:
    """完整装配 CastingEngine；ratings 缺省按 100（满技能）"""
    catalog = build_default_spell_catalog()
    schools = build_default_schools()
    mana = CasterRegistry()
    store = EffectInstanceStore()
    ledger = HealDailyLedger()
    event_port = RecordingEventPort()
    resident_port = RecordingResidentPort()
    memory_port = RecordingMemoryPort()
    rating_table = ratings or {}

    def skill_rating(caster_id: str, school_id: str) -> int:
        return rating_table.get((caster_id, school_id), 100)

    learning = LearningRegistry(
        catalog,
        skill_rating,
        lambda school_id: schools.get(school_id).learning_source_kinds,
    )
    target_table = targets or {}

    def target_resolver(target_id: str):
        return target_table.get(target_id)

    engine = CastingEngine(
        catalog=catalog,
        schools=schools,
        mana_registry=mana,
        learning=learning,
        instance_store=store,
        heal_ledger=ledger,
        event_port=event_port,
        resident_port=resident_port,
        memory_port=memory_port,
        target_resolver=target_resolver,
        skill_rating=skill_rating,
        ability_provider=lambda cid: (abilities or {}).get(cid, set()),
        item_tag_provider=lambda cid: (item_tags or {}).get(cid, set()),
        jurisdiction_of=lambda _scene: jurisdiction,
        encounter_of=lambda cid: (encounters or {}).get(cid),
        land_permission=land_permission,
        magical_item_detector=magical_item_detector,
    )
    return SimpleNamespace(
        engine=engine,
        catalog=catalog,
        schools=schools,
        mana=mana,
        learning=learning,
        store=store,
        ledger=ledger,
        event_port=event_port,
        resident_port=resident_port,
        memory_port=memory_port,
        budget=DailyCastBudget(),
        skill_rating=skill_rating,
    )


def learn(env: SimpleNamespace, caster_id: str, *spell_ids: str, max_rating: int = 100) -> None:
    """注册施法者并经初始化来源授予已学法术"""
    env.mana.register_caster(caster_id, max_rating)
    env.learning.grant_initial(caster_id, list(spell_ids), "evt.init", 0)


def command(env: SimpleNamespace, caster_id: str, spell_id: str, **overrides) -> SpellCastCommand:
    """最小可提交命令；expected_revision 默认对齐引擎当前值"""
    payload = {
        "command_id": f"cmd.{caster_id}.{spell_id}.{overrides.get('game_time', 0)}",
        "world_id": "world.test",
        "expected_revision": env.engine.revision,
        "caster_id": caster_id,
        "spell_id": spell_id,
        "scene_id": "scene.town",
        "game_time": 0,
        "game_day": 0,
        "declared_purpose": "utility",
    }
    payload.update(overrides)
    return SpellCastCommand(**payload)


def drain_mana(env: SimpleNamespace, caster_id: str, amount: int, event_prefix: str = "evt.drain") -> None:
    """经幂等消耗把 Mana 降到目标水位（驱动枯竭状态机）"""
    state = env.mana.get(caster_id)
    env.mana.consume_mana(f"{event_prefix}.{amount}", caster_id, amount, state.state_revision)
