"""
量化门槛与 G9 清单（DOC-RELEASE-011 DES-RELEASE-023、DOC-RELEASE-012 DES-RELEASE-024）

机器可读配置与判定逻辑：
- SIM30_GATE：30 游戏日 Simulation 量化门槛（runner 直接消费）
- G9_CHECKLIST：18 项验收 Check 清单（现场工具直接消费）
- ENV_MATRIX：最少 5 个环境组合
- Acceptance Record 构建与汇总判定
"""

from __future__ import annotations

from .constants import CHECKLIST_VERSION, SIMULATION_GATE_VERSION

#: DES-RELEASE-023：30 游戏日 Simulation 门槛（机器可读）
SIM30_GATE = {
    "simulation_gate_version": SIMULATION_GATE_VERSION,
    "profile": "sim_30_game_days",
    "seed_policy": "fixed_seed_fixed_fixture",
    "thresholds": {
        "process_rss_max_mib": 2048,
        "queue_depth_bounded": {"ai_requests": 64, "websocket_outbox": 1024,
                                "long_actions": 256},
        "economy_conservation_violations": 0,
        "resident_stuck_max_game_hours": 6,
        "relationship_drift_abs_max": 40,
        "active_quests_max": 24,
        "world_storage_growth_max_mib": 512,
        "invariant_violations": 0,
        "unrecovered_crash_injections": 0,
    },
    "checks": [
        {"check_id": "sim30.memory", "metric": "process_rss_max_mib",
         "source": "runtime_sampler"},
        {"check_id": "sim30.queues", "metric": "queue_depth_bounded",
         "source": "runtime_sampler"},
        {"check_id": "sim30.economy", "metric": "economy_conservation_violations",
         "source": "TEST-ECON-045, TEST-ECON-048"},
        {"check_id": "sim30.stuck", "metric": "resident_stuck_max_game_hours",
         "source": "scheduler_progress_audit"},
        {"check_id": "sim30.drift", "metric": "relationship_drift_abs_max",
         "source": "memory_social_audit"},
        {"check_id": "sim30.quests", "metric": "active_quests_max",
         "source": "event_director_audit"},
        {"check_id": "sim30.storage", "metric": "world_storage_growth_max_mib",
         "source": "release_storage_audit"},
        {"check_id": "sim30.invariants", "metric": "invariant_violations",
         "source": "DOC-FOUNDATION-005 recovery/periodic audit"},
        {"check_id": "sim30.crash", "metric": "unrecovered_crash_injections",
         "source": "TEST-RELEASE-021"},
    ],
}


def evaluate_sim30(metrics: dict) -> list[str]:
    """RULE-RELEASE-082：逐项比对门槛，任一超限即失败；返回超限 check_id"""
    thresholds = SIM30_GATE["thresholds"]
    violations: list[str] = []
    for check in SIM30_GATE["checks"]:
        metric = check["metric"]
        limit = thresholds[metric]
        value = metrics.get(metric)
        if value is None:
            violations.append(check["check_id"] + ":missing")
            continue
        if isinstance(limit, dict):
            for key, bound in limit.items():
                if value.get(key, bound + 1) > bound:
                    violations.append(check["check_id"])
                    break
        elif value > limit:
            violations.append(check["check_id"])
    return violations


#: DOC-RELEASE-011 §5.3：Browser E2E 固定 14 项场景
E2E_SCENARIOS = (
    "启动进入", "创建世界", "角色移动", "碰撞阻挡", "对话交流", "进入室内",
    "地图切换", "镇长模式", "建筑建造", "回合战斗", "手动存档", "刷新恢复",
    "全屏提示与切换", "保存退出",
)

#: DOC-RELEASE-011 §5.1：八层定义
TEST_LAYERS = (
    {"layer": "Unit", "trigger": "per-commit"},
    {"layer": "Property", "trigger": "per-commit"},
    {"layer": "Contract", "trigger": "per-commit"},
    {"layer": "Integration", "trigger": "nightly"},
    {"layer": "Simulation", "trigger": "nightly-1d/rc-7d-30d"},
    {"layer": "Browser E2E", "trigger": "nightly-subset/rc-full"},
    {"layer": "Visual QA", "trigger": "release-candidate"},
    {"layer": "Packaged Release", "trigger": "release-candidate"},
)

#: DES-RELEASE-024：Environment Matrix 最少 5 组合
ENV_MATRIX = (
    {"env_id": "ENV-1", "os": "Windows 10 22H2", "user": "ASCII",
     "path": "C:\\Games\\AI-Town\\"},
    {"env_id": "ENV-2", "os": "Windows 10 22H2", "user": "中文",
     "path": "C:\\游戏 测试\\AI 小镇\\"},
    {"env_id": "ENV-3", "os": "Windows 11", "user": "ASCII",
     "path": "%USERPROFILE%\\Desktop\\AI-Town\\"},
    {"env_id": "ENV-4", "os": "Windows 11", "user": "中文",
     "path": "D:\\我的 游戏(新)\\AI-Town\\"},
    {"env_id": "ENV-5", "os": "Windows 11", "user": "中文",
     "path": "ENV-4 同机：二次启动、停止脚本与卸载场景"},
)

#: DOC-RELEASE-012 §5.2：G9 Check 清单（18 项）
G9_CHECKLIST = {
    "checklist_version": CHECKLIST_VERSION,
    "gate": "G9",
    "requires": ["release-candidate-suite-green"],
    "checks": [
        {"check_id": "G9-CHK-001", "mode": "auto",
         "title": "机器干净性断言：PATH 与注册表无 Python/Node/Git"},
        {"check_id": "G9-CHK-002", "mode": "auto",
         "title": "release-manifest 逐文件哈希复算通过"},
        {"check_id": "G9-CHK-003", "mode": "manual",
         "title": "解压到矩阵指定路径，双击 启动AI小镇.bat"},
        {"check_id": "G9-CHK-004", "mode": "auto",
         "title": "冷启动 <= 60 s 达 ready，浏览器自动打开游戏页"},
        {"check_id": "G9-CHK-005", "mode": "auto",
         "title": "版本三方比对：manifest = /api/health = 构建源 commit"},
        {"check_id": "G9-CHK-006", "mode": "manual",
         "title": "首次进入出现 F11 与界面全屏按钮提示，切换全屏成功"},
        {"check_id": "G9-CHK-007", "mode": "manual",
         "title": "创建新世界并进入：移动、碰撞、对话、进入室内、地图切换各执行一次"},
        {"check_id": "G9-CHK-008", "mode": "manual",
         "title": "切换镇长模式执行一项治理操作；返回居民模式"},
        {"check_id": "G9-CHK-009", "mode": "manual",
         "title": "触发一场回合战斗并正常结束"},
        {"check_id": "G9-CHK-010", "mode": "manual",
         "title": "手动存档到 slot_1；刷新浏览器后世界恢复一致"},
        {"check_id": "G9-CHK-011", "mode": "auto",
         "title": "配置 Canary Key 后游玩 10 分钟，会话后 Secret 扫描全净"},
        {"check_id": "G9-CHK-012", "mode": "manual",
         "title": "运行中二次双击：不出现第二实例，浏览器聚焦现有页面"},
        {"check_id": "G9-CHK-013", "mode": "manual",
         "title": "托盘 保存并退出：进程退出、-wal 为 0、再次启动从存档恢复"},
        {"check_id": "G9-CHK-014", "mode": "manual",
         "title": "杀掉托盘后用 停止AI小镇.bat 安全停止"},
        {"check_id": "G9-CHK-015", "mode": "auto",
         "title": "licenses 目录存在且 THIRD-PARTY-NOTICES 覆盖依赖清单"},
        {"check_id": "G9-CHK-016", "mode": "manual",
         "title": "README-开始游戏.txt 记事本打开中文正常"},
        {"check_id": "G9-CHK-017", "mode": "auto",
         "title": "断网环境下启动与游玩可用（Utility AI 降级），无未处理异常"},
        {"check_id": "G9-CHK-018", "mode": "manual",
         "title": "删除包目录（卸载）后用户数据仍在；重新解压新包后世界可继续"},
    ],
}

#: 启动性能阈值（RULE-RELEASE-089）
STARTUP_BUDGETS = {"cold_start_max_seconds": 60,
                   "second_start_max_seconds": 20}

#: RULE-RELEASE-083：Simulation × Recovery 固定 crash 注入点集合
CRASH_INJECTION_POINTS = (
    "transaction_pre_commit",
    "transaction_post_commit",
    "snapshot_write_midway",
    "migration_between_steps",
    "branch_on_load_between_steps",
    "shutdown_sequence_stages",
)

#: 开发工具名单（RULE-RELEASE-086 干净机器断言）
_DEV_TOOL_NAMES = ("python", "python3", "node", "npm", "git")


def real_model_enabled(env: dict | None = None) -> bool:
    """RULE-RELEASE-080：真实 DeepSeek 唯一开关 AI_TOWN_REAL_MODEL（canonical）"""
    import os
    env = env if env is not None else os.environ
    return env.get("AI_TOWN_REAL_MODEL") == "1"


def assert_clean_machine(path_entries: list[str]) -> list[str]:
    """RULE-RELEASE-086：PATH 无 Python/Node/Git；返回发现的污染项（空=干净）"""
    polluted: list[str] = []
    for entry in path_entries:
        lowered = entry.lower()
        for tool in _DEV_TOOL_NAMES:
            if tool in lowered:
                polluted.append(entry)
                break
    return sorted(set(polluted))


def build_acceptance_record(*, package_version: str, build_id: str,
                            executed_at: str, environments: list,
                            rerun_of=None, rerun_reason=None) -> dict:
    """DOC-RELEASE-012 §5.3 Acceptance Record"""
    record = {
        "record_format_version": 1,
        "gate": "G9",
        "package_version": package_version,
        "build_id": build_id,
        "executed_at": executed_at,
        "environments": environments,
        "rerun_of": rerun_of,
        "rerun_reason": rerun_reason,
    }
    record["outcome"] = summarize_outcome(record)["outcome"]
    return record


def summarize_outcome(record: dict) -> dict:
    """RULE-RELEASE-088：任何 fail 或未执行项都使 G9 不通过；
    outcome 仅当全部环境 × 全部 check 为 pass 时为 pass"""
    required_ids = {c["check_id"] for c in G9_CHECKLIST["checks"]}
    required_envs = {e["env_id"] for e in ENV_MATRIX}
    failed: list[str] = []
    present_envs = {e["env_id"] for e in record.get("environments", [])}
    for env_id in sorted(required_envs - present_envs):
        failed.append(env_id + ":absent")
    for env in record.get("environments", []):
        results = {r["check_id"]: r for r in env.get("results", [])}
        for check_id in sorted(required_ids):
            entry = results.get(check_id)
            if entry is None:
                failed.append("{}:{}:missing".format(env["env_id"], check_id))
            elif entry.get("result") != "pass" or not entry.get("evidence"):
                failed.append("{}:{}:{}".format(
                    env["env_id"], check_id, entry.get("result", "fail")))
    return {"outcome": "fail" if failed else "pass", "failed": failed}
