"""
Quest 状态机与 Objective Matcher（DOC-EVENT-004）

- draft→offered→accepted→active→completed|failed|expired|abandoned→archived；offered→declined
- 进度只由 Matcher 消费已提交 DomainEvent；(quest_id, objective_id, event_id) 去重
- 同一事件匹配多个 Quest 全部推进；sequential 顺序只在前置完成后推进
- Deadline 经 TIME phase 0 expiry，与完成事件按 Revision 先后裁决
- 奖励只经 ECON 端口；发放失败不回滚终态，登记 Aftermath Task
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .constants import (
    QUEST_OPEN_CAP,
    QUEST_OPEN_STATES,
    QUEST_TRANSITIONS,
)
from .templates import ObjectiveSpec, QuestTemplateRegistry, TemplateError


class QuestError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class ObjectiveProgress:
    count: int = 0
    done: bool = False
    matched_event_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"count": self.count, "done": self.done,
                "matched_event_ids": list(self.matched_event_ids)}

    @staticmethod
    def from_dict(data: dict) -> "ObjectiveProgress":
        return ObjectiveProgress(
            count=data["count"], done=data["done"],
            matched_event_ids=list(data["matched_event_ids"]),
        )


@dataclass
class QuestInstance:
    quest_id: str
    quest_template_id: str
    state: str
    participants: Dict[str, List[str]]
    offered_game_time: int
    version: int = 0
    objective_progress: Dict[str, ObjectiveProgress] = field(default_factory=dict)
    deadline: Optional[int] = None
    rewards_granted: bool = False
    source_world_event_id: Optional[str] = None
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "quest_id": self.quest_id,
            "quest_template_id": self.quest_template_id,
            "state": self.state,
            "participants": copy.deepcopy(self.participants),
            "offered_game_time": self.offered_game_time,
            "version": self.version,
            "objective_progress": {k: v.to_dict() for k, v in self.objective_progress.items()},
            "deadline": self.deadline,
            "rewards_granted": self.rewards_granted,
            "source_world_event_id": self.source_world_event_id,
        }

    @staticmethod
    def from_dict(data: dict) -> "QuestInstance":
        return QuestInstance(
            schema_version=data["schema_version"],
            quest_id=data["quest_id"],
            quest_template_id=data["quest_template_id"],
            state=data["state"],
            participants=copy.deepcopy(data["participants"]),
            offered_game_time=data["offered_game_time"],
            version=data["version"],
            objective_progress={
                k: ObjectiveProgress.from_dict(v) for k, v in data["objective_progress"].items()
            },
            deadline=data["deadline"],
            rewards_granted=data["rewards_granted"],
            source_world_event_id=data["source_world_event_id"],
        )


#: 各 Objective kind 消费的 DomainEvent event_type
_OBJECTIVE_EVENT_TYPES = {
    "reach_location": "movement.arrived",
    "deliver_item": "item.delivered",
    "talk_to": "dialogue.completed",
    "craft_item": "item.crafted",
    "investigate": "clue.discovered",
    "win_encounter": "combat.encounter_resolved",
    "repair_structure": "building.repaired",
}


def match_objective(spec: ObjectiveSpec, event: dict, participant_ids: List[str]) -> bool:
    """纯函数：事件是否推进该 objective（protect/maintain 不经事件，评估期裁决）"""
    expected_type = _OBJECTIVE_EVENT_TYPES.get(spec.kind)
    if expected_type is None or event.get("event_type") != expected_type:
        return False
    payload = event.get("payload", {})
    params = spec.params
    actor = payload.get("resident_id")
    if actor is not None and participant_ids and actor not in participant_ids:
        return False
    if spec.kind == "reach_location":
        return payload.get("location_id") == params.get("location_id")
    if spec.kind == "deliver_item":
        return (
            payload.get("item_template_id") == params.get("item_template_id")
            and payload.get("to") == params.get("to")
        )
    if spec.kind == "talk_to":
        return payload.get("target_resident_id") == params.get("target_resident_id")
    if spec.kind == "craft_item":
        return payload.get("item_template_id") == params.get("item_template_id")
    if spec.kind == "investigate":
        return payload.get("clue_tag") == params.get("clue_tag")
    if spec.kind == "win_encounter":
        if params.get("encounter_id") and payload.get("encounter_id") != params["encounter_id"]:
            return False
        if params.get("winning_side") and payload.get("winning_side") != params["winning_side"]:
            return False
        allowed_endings = params.get("end_conditions")
        if allowed_endings and payload.get("end_condition") not in allowed_endings:
            return False
        return True
    if spec.kind == "repair_structure":
        return payload.get("building_id") == params.get("building_id")
    return False


class QuestEngine:
    def __init__(
        self,
        templates: QuestTemplateRegistry,
        event_log: object,
        id_factory: Callable[[], str],
        econ_port: object,
        aftermath_registrar: Optional[Callable[[str, str, dict, int], str]] = None,
    ) -> None:
        self._templates = templates
        self._log = event_log
        self._id_factory = id_factory
        self._econ = econ_port
        #: 奖励发放失败时的善后登记（world_event_id 可为 quest 来源事件）
        self._aftermath_registrar = aftermath_registrar
        self._quests: Dict[str, QuestInstance] = {}
        self._command_results: Dict[str, dict] = {}
        self._occurrences: Dict[str, dict] = {}
        #: protect_target / maintain_condition 的评估提供者（测试注入）
        self.protect_target_alive: Callable[[str], bool] = lambda _target: True
        self.maintain_condition_holds: Callable[[dict], bool] = lambda _params: True

    # -- 查询 ------------------------------------------------------------

    def get(self, quest_id: str) -> QuestInstance:
        try:
            return self._quests[quest_id]
        except KeyError:
            raise QuestError("quest_unknown", quest_id) from None

    def open_quests(self) -> List[QuestInstance]:
        return [q for q in self._quests.values() if q.state in QUEST_OPEN_STATES]

    def all(self) -> List[QuestInstance]:
        return list(self._quests.values())

    # -- 生命周期 ---------------------------------------------------------

    def create_offer(
        self,
        command_id: str,
        quest_template_id: str,
        participants: Dict[str, List[str]],
        game_time: int,
        source_world_event_id: Optional[str] = None,
    ) -> QuestInstance:
        if command_id in self._command_results:
            return self.get(self._command_results[command_id]["quest_id"])
        try:
            template = self._templates.get(quest_template_id)
        except TemplateError as exc:
            raise QuestError(exc.code, str(exc)) from None
        for role, min_count in template.participant_roles.items():
            if len(participants.get(role, [])) < min_count:
                raise QuestError("participant_invalid", f"role {role} needs {min_count}")
        if len(self.open_quests()) >= QUEST_OPEN_CAP:
            raise QuestError("quest_open_cap_exceeded", str(QUEST_OPEN_CAP))
        quest = QuestInstance(
            quest_id=self._id_factory(),
            quest_template_id=quest_template_id,
            state="offered",
            participants=copy.deepcopy(participants),
            offered_game_time=game_time,
            objective_progress={
                spec.objective_id: ObjectiveProgress() for spec in template.objectives
            },
            deadline=(
                game_time + template.deadline_game_minutes
                if template.deadline_game_minutes is not None else None
            ),
            source_world_event_id=source_world_event_id,
        )
        # draft 为瞬时态：创建即 offered（draft→offered 在同一命令内完成）
        self._quests[quest.quest_id] = quest
        self._log.append(
            "quest.offered",
            {"quest_id": quest.quest_id, "quest_template_id": quest_template_id,
             "participants": copy.deepcopy(participants),
             "source_world_event_id": source_world_event_id},
            game_time, caused_by_command_id=command_id,
        )
        self._command_results[command_id] = {"quest_id": quest.quest_id}
        return quest

    def _transition(self, quest: QuestInstance, target: str, game_time: int,
                    reason: Optional[str] = None) -> QuestInstance:
        if (quest.state, target) not in QUEST_TRANSITIONS:
            raise QuestError("state_transition_illegal", f"{quest.state} → {target}")
        quest.state = target
        quest.version += 1
        self._log.append(
            f"quest.{target}",
            {"quest_id": quest.quest_id, "reason": reason},
            game_time,
        )
        return quest

    def respond(self, command_id: str, quest_id: str, accept: bool,
                game_time: int, expected_version: int) -> QuestInstance:
        if command_id in self._command_results:
            return self.get(self._command_results[command_id]["quest_id"])
        quest = self.get(quest_id)
        if quest.version != expected_version:
            raise QuestError("version_stale", f"{quest.version} != {expected_version}")
        if quest.state != "offered":
            raise QuestError("offer_taken", quest.state)
        if quest.deadline is not None and game_time > quest.deadline:
            raise QuestError("deadline_passed", quest_id)
        self._transition(quest, "accepted" if accept else "declined", game_time)
        self._command_results[command_id] = {"quest_id": quest_id}
        return quest

    def begin(self, command_id: str, quest_id: str, game_time: int,
              expected_version: int) -> QuestInstance:
        if command_id in self._command_results:
            return self.get(self._command_results[command_id]["quest_id"])
        quest = self.get(quest_id)
        if quest.version != expected_version:
            raise QuestError("version_stale", f"{quest.version} != {expected_version}")
        if quest.deadline is not None and game_time > quest.deadline:
            raise QuestError("deadline_passed", quest_id)
        self._transition(quest, "active", game_time)
        self._command_results[command_id] = {"quest_id": quest_id}
        return quest

    def abandon(self, command_id: str, quest_id: str, game_time: int,
                expected_version: int) -> QuestInstance:
        if command_id in self._command_results:
            return self.get(self._command_results[command_id]["quest_id"])
        quest = self.get(quest_id)
        if quest.version != expected_version:
            raise QuestError("version_stale", f"{quest.version} != {expected_version}")
        self._transition(quest, "abandoned", game_time)
        self._command_results[command_id] = {"quest_id": quest_id}
        return quest

    def archive(self, command_id: str, quest_id: str, game_time: int,
                expected_version: int) -> QuestInstance:
        if command_id in self._command_results:
            return self.get(self._command_results[command_id]["quest_id"])
        quest = self.get(quest_id)
        if quest.version != expected_version:
            raise QuestError("version_stale", f"{quest.version} != {expected_version}")
        self._transition(quest, "archived", game_time)
        self._command_results[command_id] = {"quest_id": quest_id}
        return quest

    # -- Matcher ------------------------------------------------------------

    def submit_domain_event(self, event: dict, game_time: int) -> List[str]:
        """
        消费一条已提交 DomainEvent；同一事件匹配多个 Quest 全部推进。
        返回被推进的 quest_id 列表。
        """
        progressed: List[str] = []
        event_id = event.get("event_id")
        for quest in self._quests.values():
            if quest.state != "active":
                continue
            template = self._templates.get(quest.quest_template_id)
            participant_ids = [pid for ids in quest.participants.values() for pid in ids]
            changed = False
            for index, spec in enumerate(template.objectives):
                progress = quest.objective_progress[spec.objective_id]
                if progress.done or event_id in progress.matched_event_ids:
                    continue
                if template.objective_ordering == "sequential" and index > 0:
                    previous = template.objectives[index - 1]
                    if not quest.objective_progress[previous.objective_id].done:
                        continue
                if not match_objective(spec, event, participant_ids):
                    continue
                progress.matched_event_ids.append(event_id)
                progress.count += 1
                if progress.count >= spec.count_required:
                    progress.done = True
                changed = True
            if changed:
                quest.version += 1
                self._log.append(
                    "quest.objective_progressed",
                    {"quest_id": quest.quest_id, "event_id": event_id},
                    game_time,
                )
                progressed.append(quest.quest_id)
                self._maybe_complete(quest, game_time)
        return progressed

    def _maybe_complete(self, quest: QuestInstance, game_time: int) -> None:
        if quest.state != "active":
            return
        template = self._templates.get(quest.quest_template_id)
        for spec in template.objectives:
            progress = quest.objective_progress[spec.objective_id]
            if progress.done:
                continue
            if spec.kind == "protect_target":
                # 守护类：其余全部完成时目标仍存活 → 判定完成
                others_done = all(
                    quest.objective_progress[o.objective_id].done
                    for o in template.objectives if o.objective_id != spec.objective_id
                )
                if others_done and self.protect_target_alive(spec.params.get("target_id", "")):
                    progress.done = True
            elif spec.kind == "maintain_condition":
                others_done = all(
                    quest.objective_progress[o.objective_id].done
                    for o in template.objectives if o.objective_id != spec.objective_id
                )
                if others_done and self.maintain_condition_holds(spec.params):
                    progress.done = True
            if not progress.done:
                return
        self._transition(quest, "completed", game_time, reason="objectives_done")
        self._grant_rewards(quest, game_time)

    def _grant_rewards(self, quest: QuestInstance, game_time: int) -> None:
        """奖励只经 ECON 端口；发放失败不回滚终态，登记 Aftermath Task"""
        template = self._templates.get(quest.quest_template_id)
        failures: List[str] = []
        for reward in template.rewards:
            for role, ids in quest.participants.items():
                for resident_id in ids:
                    try:
                        self._econ.grant_reward(
                            resident_id, reward.reward_kind, dict(reward.parameters),
                            evidence_id=quest.quest_id,
                        )
                    except Exception:
                        failures.append(f"{reward.reward_kind}→{resident_id}")
        quest.rewards_granted = not failures
        if failures and self._aftermath_registrar is not None:
            self._aftermath_registrar(
                quest.source_world_event_id or "quest",
                "compensation",
                {"quest_id": quest.quest_id, "failed_rewards": failures},
                game_time,
            )
            self._log.append(
                "quest.reward_failed_aftermath_registered",
                {"quest_id": quest.quest_id, "failures": failures},
                game_time,
            )

    # -- Deadline（TIME phase 0 expiry） ---------------------------------------

    def on_deadline(self, occurrence: dict) -> dict:
        """
        occurrence: {occurrence_key, kind=quest_deadline, game_time, payload{quest_id}}
        offered → expired；accepted/active 按 failure_policy → failed/expired；
        与完成事件按 Revision 先后裁决：已完成/归档的 quest 跳过
        """
        key = occurrence["occurrence_key"]
        if key in self._occurrences:
            return {"status": "replayed", "result": self._occurrences[key]}
        game_time = occurrence["game_time"]
        quest = self.get(occurrence["payload"]["quest_id"])
        if quest.state not in QUEST_OPEN_STATES:
            result = {"status": "skipped", "state": quest.state}
        elif quest.deadline is None or game_time < quest.deadline:
            result = {"status": "skipped", "reason": "deadline_not_reached"}
        else:
            template = self._templates.get(quest.quest_template_id)
            if quest.state == "offered":
                target = "expired"
            else:
                target = template.failure_policy
            self._transition(quest, target, game_time, reason="deadline_passed")
            result = {"status": target}
        self._occurrences[key] = result
        return {"status": "processed", "result": result}

    # -- 导出/导入 -----------------------------------------------------------

    def export_state(self) -> dict:
        return {
            "quests": {qid: q.to_dict() for qid, q in self._quests.items()},
            "command_results": copy.deepcopy(self._command_results),
            "occurrences": copy.deepcopy(self._occurrences),
        }

    def import_state(self, data: dict) -> None:
        self._quests = {qid: QuestInstance.from_dict(q) for qid, q in data["quests"].items()}
        self._command_results = copy.deepcopy(data["command_results"])
        self._occurrences = copy.deepcopy(data["occurrences"])
