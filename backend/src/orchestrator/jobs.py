"""
长任务 Job 资源（DOC-BACKEND-004 RULE-BACKEND-024 / §7）

- 预计超过 1000 real ms 的操作返回 202 + Job Resource，Client 轮询，不长挂连接
- state ∈ queued/running/succeeded/failed；成功含 result_ref（本地文件句柄 ID）
- Job 完成前进程重启：标记 failed(reason_code=process_restarted)，不跨进程恢复
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from ..foundation.errors import ApiError

JOB_STATES = frozenset({"queued", "running", "succeeded", "failed"})

JOB_TRANSITIONS = frozenset({
    ("queued", "running"),
    ("queued", "failed"),
    ("running", "succeeded"),
    ("running", "failed"),
})


@dataclass
class Job:
    job_id: str
    kind: str
    state: str = "queued"
    result_ref: Optional[str] = None
    reason_code: Optional[str] = None

    def to_resource(self) -> dict:
        return {
            "schema_version": 1,
            "job_id": self.job_id,
            "kind": self.kind,
            "state": self.state,
            "result_ref": self.result_ref,
            "reason_code": self.reason_code,
        }


class JobRegistry:
    def __init__(self, id_factory: Callable[[], str]) -> None:
        self._id_factory = id_factory
        self._jobs: Dict[str, Job] = {}

    def create(self, kind: str) -> Job:
        job = Job(job_id=self._id_factory(), kind=kind)
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise ApiError("BACKEND_NOT_FOUND", {"job_id": job_id})
        return job

    def _transition(self, job: Job, target: str) -> Job:
        if (job.state, target) not in JOB_TRANSITIONS:
            raise ApiError("BACKEND_CONFLICT_STATE",
                           {"job_id": job.job_id,
                            "reason_code": f"{job.state}→{target}"})
        job.state = target
        return job

    def start(self, job_id: str) -> Job:
        return self._transition(self.get(job_id), "running")

    def succeed(self, job_id: str, result_ref: str) -> Job:
        job = self._transition(self.get(job_id), "succeeded")
        job.result_ref = result_ref
        return job

    def fail(self, job_id: str, reason_code: str) -> Job:
        job = self._transition(self.get(job_id), "failed")
        job.reason_code = reason_code
        return job

    def mark_process_restarted(self) -> int:
        """进程重启：全部未完成 Job 标记 failed(process_restarted)"""
        marked = 0
        for job in self._jobs.values():
            if job.state in ("queued", "running"):
                job.state = "failed"
                job.reason_code = "process_restarted"
                marked += 1
        return marked
