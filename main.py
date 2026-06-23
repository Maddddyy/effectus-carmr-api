"""
Effectus CARMR Extraction API
FastAPI + SSE - agentic CARMR extraction pipeline.
"""
import asyncio
import json
import os
import uuid
import logging
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "https://effectus.madhvendra.com")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))

app = FastAPI(
    title="Effectus CARMR Extraction API",
    description=(
        "Agentic pipeline: board documents to structured CARMR records. "
        "v1.2.0 adds fallacy-driven assumption extraction (three-pass assumptions stage). "
        "v1.3.0 revamps Stage 5 (Meaning): intra-document definition-in-use detection with "
        "four scenarios (Contested Meanings, Classic Ambiguity, Hidden Divergence, Undefined Term), "
        "deterministic semantic divergence scoring via sentence-transformers with lexical fallback, "
        "and verbatim evidence quote verification. External web search removed from Meaning stage. "
        "MeaningTerm model extended with definitionsInUse, divergence, scenarioType, and related fields."
    ),
    version="1.3.0",
)
# CORS - allow FE origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Type"],
)

# ── Job store ──────────────────────────────────────────────────────────────────
from jobs.store import job_store


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Health check."""
    api_key_set = bool(os.getenv("ANTHROPIC_API_KEY"))
    return {
        "status": "ok",
        "api_key_configured": api_key_set,
        "model": os.getenv("OPUS_MODEL", "claude-opus-4-5"),
        "allowed_origin": ALLOWED_ORIGIN,
    }


@app.post("/api/jobs")
async def create_job(files: List[UploadFile] = File(...)):
    """
    Upload one or more documents. Returns a job_id immediately.
    Then connect to /api/jobs/{job_id}/stream for SSE progress.
    """
    if not files:
        raise HTTPException(400, "No files provided")

    # Validate and read files
    file_data = []
    for f in files:
        content = await f.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_UPLOAD_MB:
            raise HTTPException(413, f"File {f.filename} is {size_mb:.1f}MB, max {MAX_UPLOAD_MB}MB")
        file_data.append((f.filename or "upload", content))

    job_id = str(uuid.uuid4())
    filenames = [name for name, _ in file_data]
    job_store.create(job_id, filenames)

    # Store file data temporarily for stream pickup
    _pending_jobs[job_id] = file_data

    logger.info(f"Job {job_id} created: {filenames}")

    return {
        "job_id": job_id,
        "status": "queued",
        "files": filenames,
        "stream_url": f"/api/jobs/{job_id}/stream",
    }


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    """
    SSE stream for a job. Stays open until pipeline completes or errors.
    Connect immediately after POST /api/jobs.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    file_data = _pending_jobs.pop(job_id, None)
    if not file_data:
        # Job already running or complete
        if job.status == "complete" and job.result:
            async def already_done():
                yield f"event: complete\ndata: {json.dumps(job.result)}\n\n"
            return StreamingResponse(already_done(), media_type="text/event-stream")
        elif job.status == "error":
            async def error_stream():
                yield f"event: error\ndata: {json.dumps({'message': job.error})}\n\n"
            return StreamingResponse(error_stream(), media_type="text/event-stream")
        else:
            raise HTTPException(409, "Job stream already consumed. Reconnect not supported yet.")

    job_store.update(job_id, status="running")

    async def pipeline_stream():
        from pipeline.orchestrator import run_pipeline
        final_result = None
        try:
            async for event_str in run_pipeline(job_id, file_data):
                # Track current stage from events
                try:
                    event_lines = event_str.strip().split("\n")
                    for line in event_lines:
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            if "stage" in data:
                                job_store.update(job_id, current_stage=data["stage"])
                except Exception:
                    pass

                yield event_str

                # Capture complete event for result storage
                if "event: complete" in event_str:
                    try:
                        for line in event_str.strip().split("\n"):
                            if line.startswith("data: "):
                                final_result = json.loads(line[6:])
                    except Exception:
                        pass

            job_store.update(
                job_id,
                status="complete",
                result=final_result,
                progress_pct=100.0,
            )

        except Exception as e:
            logger.exception(f"Pipeline error for job {job_id}: {e}")
            error_event = f"event: error\ndata: {json.dumps({'message': str(e), 'job_id': job_id})}\n\n"
            yield error_event
            job_store.update(job_id, status="error", error=str(e))

    return StreamingResponse(
        pipeline_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@app.get("/api/jobs/{job_id}/status")
async def job_status(job_id: str):
    """Poll job status."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return {
        "job_id": job_id,
        "status": job.status,
        "current_stage": job.current_stage,
        "progress_pct": job.progress_pct,
        "filenames": job.filenames,
    }


@app.get("/api/jobs/{job_id}/result")
async def job_result(job_id: str):
    """Get final CARMR result when complete."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if job.status != "complete":
        raise HTTPException(202, f"Job not complete yet. Status: {job.status}")
    return job.result


# In-memory pending jobs buffer (files waiting for stream pickup)
_pending_jobs: dict[str, list] = {}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level="info")
