"""
魔法学习与成长（DOC-MAGIC-006）

- REQ-MAGIC-011：SchoolSkill 归 RESIDENT，MAGIC 不维护第二套技能数值
- REQ-MAGIC-012：learned 只能由已提交学习完成事件产生
- RULE-MAGIC-029：unknown → studying → learned，无降级
- RULE-MAGIC-031：学习会话是排他长行动，检查点重验来源
- RULE-MAGIC-033：施法与检查点 XP 按 source_event_id 幂等
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from ..foundation import generate_ulid
from .constants import KNOWLEDGE_ENTRIES_CAP, KnowledgeState, SourceKind
from .spells import SpellCatalog, study_work_units_for


class LearningError(Exception):
    """学习流程失败；code 为稳定 reason code"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class KnowledgeEntry:
    """DES-MAGIC-006 的 per-caster 法术掌握记录"""

    spell_id: str
    state: KnowledgeState
    source_kind: SourceKind
    source_ref: str
    study_progress: int = 0
    required_work_units: int = 0
    study_long_action_id: Optional[str] = None
    source_available: bool = True
    learned_at_game_time: Optional[int] = None


@dataclass
class SpellKnowledge:
    caster_id: str
    entries: Dict[str, KnowledgeEntry] = field(default_factory=dict)
    knowledge_revision: int = 0
    knowledge_schema_version: int = 1


class LearningRegistry:
    """SpellKnowledge 状态机与三类学习来源"""

    def __init__(
        self,
        catalog: SpellCatalog,
        skill_rating: Callable[[str, str], int],
        school_learning_kinds: Callable[[str], Tuple[SourceKind, ...]],
        xp_sink: Optional[Callable[[str, str, str], None]] = None,
    ) -> None:
        self._catalog = catalog
        # (caster_id, school_id) -> rating；RESIDENT 技能投影的只读端口
        self._skill_rating = skill_rating
        self._school_learning_kinds = school_learning_kinds
        # RULE-MAGIC-033：XP 经 RESIDENT apply_skill_practice 幂等提交
        self._xp_sink = xp_sink or (lambda _c, _s, _e: None)
        self._knowledge: Dict[str, SpellKnowledge] = {}
        self._xp_events: Set[str] = set()
        self._command_results: Dict[str, KnowledgeEntry] = {}

    def knowledge_of(self, caster_id: str) -> SpellKnowledge:
        return self._knowledge.setdefault(caster_id, SpellKnowledge(caster_id))

    def is_learned(self, caster_id: str, spell_id: str) -> bool:
        entry = self.knowledge_of(caster_id).entries.get(spell_id)
        return entry is not None and entry.state is KnowledgeState.LEARNED

    def grant_initial(
        self,
        caster_id: str,
        spell_ids: List[str],
        source_event_id: str,
        game_time: int,
    ) -> None:
        """世界初始化预置：构建期校验门槛满足，同样携带 source event"""
        for spell_id in spell_ids:
            spell = self._catalog.get(spell_id)
            rating = self._skill_rating(caster_id, spell.school_id)
            if rating < spell.prerequisites["min_school_skill_rating"]:
                raise LearningError(
                    "MAGIC_STUDY_PREREQUISITE_MISSING",
                    f"template grants {spell_id} without rating {spell.prerequisites['min_school_skill_rating']}",
                )
            knowledge = self.knowledge_of(caster_id)
            knowledge.entries[spell_id] = KnowledgeEntry(
                spell_id=spell_id,
                state=KnowledgeState.LEARNED,
                source_kind=SourceKind.INITIALIZATION,
                source_ref=source_event_id,
                learned_at_game_time=game_time,
            )
            knowledge.knowledge_revision += 1

    def begin_study(
        self,
        command_id: str,
        caster_id: str,
        spell_id: str,
        source_kind: SourceKind,
        source_ref: str,
        source_available: bool,
    ) -> KnowledgeEntry:
        """RULE-MAGIC-030：进入 studying 的前置校验"""
        if command_id in self._command_results:
            return self._command_results[command_id]
        spell = self._catalog.get(spell_id)
        knowledge = self.knowledge_of(caster_id)
        existing = knowledge.entries.get(spell_id)
        if existing is not None and existing.state is KnowledgeState.LEARNED:
            raise LearningError("MAGIC_ALREADY_LEARNED", spell_id)
        if existing is not None and existing.state is KnowledgeState.STUDYING and existing.source_available:
            raise LearningError("magic_study_session_conflict", spell_id)
        if len(knowledge.entries) >= KNOWLEDGE_ENTRIES_CAP and existing is None:
            raise LearningError("magic_knowledge_cap", caster_id)
        rating = self._skill_rating(caster_id, spell.school_id)
        if rating < spell.prerequisites["min_school_skill_rating"]:
            raise LearningError("MAGIC_STUDY_PREREQUISITE_MISSING", spell_id)
        allowed_kinds = self._school_learning_kinds(spell.school_id)
        if source_kind not in allowed_kinds:
            raise LearningError(
                "MAGIC_STUDY_SOURCE_UNAVAILABLE",
                f"{source_kind.value} not in {sorted(k.value for k in allowed_kinds)}",
            )
        if not source_available:
            raise LearningError("MAGIC_STUDY_SOURCE_UNAVAILABLE", source_ref)
        entry = KnowledgeEntry(
            spell_id=spell_id,
            state=KnowledgeState.STUDYING,
            source_kind=source_kind,
            source_ref=source_ref,
            study_progress=existing.study_progress if existing else 0,
            required_work_units=study_work_units_for(spell),
            study_long_action_id=generate_ulid(),
        )
        knowledge.entries[spell_id] = entry
        knowledge.knowledge_revision += 1
        self._command_results[command_id] = entry
        return entry

    def complete_study_checkpoint(
        self,
        caster_id: str,
        spell_id: str,
        game_time: int,
        source_available: bool = True,
        xp_event_id: Optional[str] = None,
    ) -> KnowledgeEntry:
        """RULE-MAGIC-031：检查点重验来源；进度足够即 learned"""
        knowledge = self.knowledge_of(caster_id)
        entry = knowledge.entries.get(spell_id)
        if entry is None or entry.state is not KnowledgeState.STUDYING:
            raise LearningError("magic_study_session_unknown", spell_id)
        if not source_available:
            # 来源失效：会话中断、进度保留，重新取得后可 resume
            entry.source_available = False
            raise LearningError("MAGIC_STUDY_SOURCE_UNAVAILABLE", entry.source_ref)
        entry.source_available = True
        entry.study_progress += 1
        if xp_event_id is not None:
            self.grant_cast_xp(caster_id, self._catalog.get(spell_id).school_id, xp_event_id)
        if entry.study_progress >= entry.required_work_units:
            entry.state = KnowledgeState.LEARNED
            entry.learned_at_game_time = game_time
            entry.study_long_action_id = None
        knowledge.knowledge_revision += 1
        return entry

    def resume_study(self, caster_id: str, spell_id: str, source_available: bool) -> KnowledgeEntry:
        """中断会话恢复：来源重新可用即可继续，进度不丢"""
        knowledge = self.knowledge_of(caster_id)
        entry = knowledge.entries.get(spell_id)
        if entry is None or entry.state is not KnowledgeState.STUDYING:
            raise LearningError("magic_study_session_unknown", spell_id)
        if not source_available:
            raise LearningError("MAGIC_STUDY_SOURCE_UNAVAILABLE", entry.source_ref)
        entry.source_available = True
        knowledge.knowledge_revision += 1
        return entry

    def grant_cast_xp(self, caster_id: str, school_id: str, source_event_id: str) -> None:
        """RULE-MAGIC-033：施法/检查点 XP 按 source_event_id 幂等去重"""
        if source_event_id in self._xp_events:
            return
        self._xp_events.add(source_event_id)
        self._xp_sink(caster_id, school_id, source_event_id)

    @property
    def xp_event_count(self) -> int:
        return len(self._xp_events)
