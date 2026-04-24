"""
In-memory job store with TTL. Tracks job status and final results.
"""
import asyncio
import time
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Job:
    job_id: str
    status: str = "queued"       # queued | running | complete | error
    current_stage: str = ""
    progress_pct: float = 0.0
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    filenames: list = field(default_factory=list)


class JobStore:
    def __init__(self, ttl_seconds: int = 3600):
        self._jobs: dict[str, Job] = {}
        self._ttl = ttl_seconds

    def create(self, job_id: str, filenames: list) -> Job:
        job = Job(job_id=job_id, filenames=filenames)
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        self._evict_expired()
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs):
        job = self._jobs.get(job_id)
        if job:
            for k, v in kwargs.items():
                setattr(job, k, v)

    def _evict_expired(self):
        now = time.time()
        expired = [jid for jid, j in self._jobs.items()
                   if now - j.started_at > self._ttl]
        for jid in expired:
            del self._jobs[jid]


# Singleton
job_store = JobStore()
