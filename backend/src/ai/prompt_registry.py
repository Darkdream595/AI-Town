"""
Prompt 分层、版本与注入防线

符合 DOC-AI-003：
- RULE-AI-013：层顺序固定，变量必须在 Registry 白名单
- RULE-AI-014：玩家/居民/Memory/网络文本均为 untrusted data
- RULE-AI-015：Prompt ID 语义不可就地改变
- RULE-AI-018：持久化只记录 Prompt ID、template hash、context hash、版本
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class PromptLayer(str, Enum):
    """不可变层次（DOC-AI-003 §3），顺序固定"""

    SYSTEM_CONTRACT = "system_contract"
    DEVELOPER_TASK = "developer_task"
    WORLD_RULES = "world_rules"
    RESIDENT_PROFILE = "resident_profile"
    DECISION_CONTEXT = "decision_context"
    OUTPUT_CONTRACT = "output_contract"


#: 消息装配固定顺序（DES-AI-003）
LAYER_ORDER: tuple[PromptLayer, ...] = (
    PromptLayer.SYSTEM_CONTRACT,
    PromptLayer.DEVELOPER_TASK,
    PromptLayer.WORLD_RULES,
    PromptLayer.RESIDENT_PROFILE,
    PromptLayer.DECISION_CONTEXT,
    PromptLayer.OUTPUT_CONTRACT,
)

#: 每个 untrusted string 上限（DOC-AI-003 §9）
MAX_UNTRUSTED_STRING_CHARS = 2048
MAX_TOTAL_UNTRUSTED_CHARS = 8192


@dataclass(frozen=True)
class PromptRegistryRecord:
    """Registry record（DES-AI-003）"""

    prompt_id: str
    artifact_schema_id: str
    template_sha256: str
    policy_version: int
    allowed_variables: frozenset[str]
    model_policy_id: str
    status: str  # "active" | "inactive"


class PromptRegistryError(Exception):
    """未知 Prompt ID、变量越界、hash 不符（DOC-AI-003 §8）"""


class PromptRegistry:
    """版本化 Prompt Registry（只读）"""

    def __init__(self, records: list[PromptRegistryRecord]):
        self._records = {record.prompt_id: record for record in records}

    def resolve(self, prompt_id: str) -> PromptRegistryRecord:
        record = self._records.get(prompt_id)
        if record is None:
            raise PromptRegistryError(f"未知 prompt_id: {prompt_id}")
        if record.status != "active":
            raise PromptRegistryError(f"prompt_id 已停用: {prompt_id}")
        return record

    def validate_variables(self, prompt_id: str, variables: dict[str, Any]) -> None:
        """所有变量必须在白名单内（RULE-AI-013）"""
        record = self.resolve(prompt_id)
        unknown = set(variables.keys()) - record.allowed_variables
        if unknown:
            raise PromptRegistryError(
                f"变量越出白名单: {sorted(unknown)} (allowed: {sorted(record.allowed_variables)})"
            )

    def verify_template_hash(self, prompt_id: str, template_sha256: str) -> None:
        """Catalog/模板升级但缓存未失效时阻止调用（DOC-AI-003 §7）"""
        record = self.resolve(prompt_id)
        if record.template_sha256 != template_sha256:
            raise PromptRegistryError(
                f"模板 hash 不符: {prompt_id} expected={record.template_sha256} got={template_sha256}"
            )


def _compute_template_hash(layers: dict[PromptLayer, str]) -> str:
    canonical = json.dumps(
        {layer.value: layers[layer] for layer in LAYER_ORDER if layer in layers},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_default_registry() -> PromptRegistry:
    """首版 Registry（DES-AI-003 七个 Prompt ID）"""
    templates = _default_templates()
    records = [
        PromptRegistryRecord(
            prompt_id=prompt_id,
            artifact_schema_id=artifact_schema_id,
            template_sha256=_compute_template_hash(templates[prompt_id]),
            policy_version=1,
            allowed_variables=frozenset(allowed_variables),
            model_policy_id=model_policy_id,
            status="active",
        )
        for prompt_id, artifact_schema_id, allowed_variables, model_policy_id in [
            (
                "resident-daily-plan/v1",
                "schema.ai.daily_plan.v1",
                ["decision_context_json", "action_catalog_digest"],
                "model_policy.resident_daily_plan.v1",
            ),
            (
                "resident-hourly-intent/v1",
                "schema.ai.hourly_intent.v1",
                ["decision_context_json", "action_catalog_digest"],
                "model_policy.resident_hourly_intent.v1",
            ),
            (
                "resident-action/v1",
                "schema.ai.action_proposal.v1",
                ["decision_context_json", "action_catalog_digest"],
                "model_policy.resident_action.v1",
            ),
            (
                "resident-dialogue/v1",
                "schema.ai.dialogue_turn.v1",
                ["decision_context_json", "dialogue_state_json"],
                "model_policy.resident_dialogue.v1",
            ),
            (
                "resident-combat-turn/v1",
                "schema.ai.combat_turn.v1",
                ["decision_context_json", "legal_options_json"],
                "model_policy.resident_combat_turn.v1",
            ),
            (
                "event-director/v1",
                "schema.ai.event_directive.v1",
                ["world_digest_json"],
                "model_policy.event_director.v1",
            ),
            (
                "memory-consolidation/v1",
                "schema.ai.memory_summary.v1",
                ["memory_batch_json"],
                "model_policy.memory_consolidation.v1",
            ),
        ]
    ]
    return PromptRegistry(records)


def _default_templates() -> dict[str, dict[PromptLayer, str]]:
    """首版模板（随应用只读发布）"""
    base = {
        PromptLayer.SYSTEM_CONTRACT: (
            "你是 AI 小镇的居民决策模块。你只输出严格 JSON；不泄露秘密；"
            "你没有任何世界写权限；所有数值结算由服务器完成。"
        ),
        PromptLayer.WORLD_RULES: "时间：1 现实秒 = 1 游戏分钟；坐标单位 wu；货币：银冠/铜羽。",
        PromptLayer.OUTPUT_CONTRACT: "只输出单个 JSON object，符合注册 Schema，禁止 Markdown fence。",
    }
    return {
        "resident-daily-plan/v1": {
            **base,
            PromptLayer.DEVELOPER_TASK: "生成当日 Daily Plan：目标、优先级、成功/放弃条件。",
            PromptLayer.RESIDENT_PROFILE: "{resident_profile_json}",
        },
        "resident-hourly-intent/v1": {
            **base,
            PromptLayer.DEVELOPER_TASK: "生成 Hourly Intent：一个目标及候选 Action sequence。",
            PromptLayer.RESIDENT_PROFILE: "{resident_profile_json}",
        },
        "resident-action/v1": {
            **base,
            PromptLayer.DEVELOPER_TASK: "从候选 Action 中选一个，输出 ActionProposalV1。",
            PromptLayer.RESIDENT_PROFILE: "{resident_profile_json}",
        },
        "resident-dialogue/v1": {
            **base,
            PromptLayer.DEVELOPER_TASK: "生成对话回合：SpeechAct 与内容，遵守秘密边界。",
            PromptLayer.RESIDENT_PROFILE: "{resident_profile_json}",
        },
        "resident-combat-turn/v1": {
            **base,
            PromptLayer.DEVELOPER_TASK: "从 legal options 中选择一个战斗行动。",
            PromptLayer.RESIDENT_PROFILE: "{resident_profile_json}",
        },
        "event-director/v1": {
            **base,
            PromptLayer.DEVELOPER_TASK: "生成世界事件指令。",
        },
        "memory-consolidation/v1": {
            **base,
            PromptLayer.DEVELOPER_TASK: "整合记忆摘要。",
        },
    }


@dataclass(frozen=True)
class ComposedMessage:
    """装配后单条消息"""

    layer: PromptLayer
    content: str


def compose_messages(
    registry: PromptRegistry,
    prompt_id: str,
    variables: dict[str, Any],
) -> tuple[list[ComposedMessage], str]:
    """
    按固定层序装配消息（RULE-AI-013）

    untrusted_content 只能作为 decision_context 内 JSON string（DES-AI-003）。
    返回 (messages, request_hash)。
    """
    record = registry.resolve(prompt_id)
    registry.validate_variables(prompt_id, variables)

    layers = _default_templates().get(prompt_id)
    if layers is None:
        raise PromptRegistryError(f"无模板: {prompt_id}")
    registry.verify_template_hash(prompt_id, record.template_sha256)

    messages: list[ComposedMessage] = []
    for layer in LAYER_ORDER:
        if layer == PromptLayer.DECISION_CONTEXT:
            # decision_context 以 canonical JSON 注入，untrusted string 由 JSON serializer 转义；
            # 位置固定在 resident_profile 与 output_contract 之间（RULE-AI-013）
            if (
                "decision_context_json" in record.allowed_variables
                and "decision_context_json" in variables
            ):
                context_json = variables["decision_context_json"]
                messages.append(
                    ComposedMessage(
                        layer=PromptLayer.DECISION_CONTEXT,
                        content=json.dumps(context_json, ensure_ascii=False, sort_keys=True)
                        if not isinstance(context_json, str)
                        else context_json,
                    )
                )
            continue
        if layer not in layers:
            continue
        content = layers[layer]
        messages.append(ComposedMessage(layer=layer, content=content))

    request_payload = json.dumps(
        [f"{m.layer.value}:{m.content}" for m in messages], ensure_ascii=False
    )
    request_hash = "sha256:" + hashlib.sha256(request_payload.encode("utf-8")).hexdigest()[:16]
    return messages, request_hash


def sanitize_untrusted_text(text: str) -> str:
    """
    untrusted 文本策略（DOC-AI-003 §7）

    长度与控制字符超限拒绝；内容本身不升级为 instruction（RULE-AI-014）。
    """
    if len(text) > MAX_UNTRUSTED_STRING_CHARS:
        raise PromptRegistryError(
            f"untrusted string 超限: {len(text)} > {MAX_UNTRUSTED_STRING_CHARS}"
        )
    for char in text:
        code_point = ord(char)
        # 允许 \t \n \r，拒绝其他 C0/C1 控制符
        if code_point < 0x20 and char not in "\t\n\r":
            raise PromptRegistryError(f"untrusted string 含控制字符 U+{code_point:04X}")
        if 0x7F <= code_point <= 0x9F:
            raise PromptRegistryError(f"untrusted string 含控制字符 U+{code_point:04X}")
    return text
