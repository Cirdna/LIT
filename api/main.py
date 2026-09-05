"""FastAPI service backing Stage 5 (PDF viewer click-to-jump integration).

Endpoints:
  POST /jobs            - upload a document, kick off analysis in the background
  GET  /jobs/{job_id}    - poll job status; returns the enriched CUAD JSON when done
  GET  /jobs/{job_id}/pdf - serve the standardized PDF for the frontend viewer

Run with: uvicorn api.main:app --reload
(requires `pip install -e .` from the repo root first, so `pdf_analyzer` is importable)
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pdf_analyzer.pipeline import analyze_document
from pdf_analyzer.stage2_vlm import build_vlm_backend

DATA_DIR = Path(__file__).resolve().parent.parent / ".jobs"
DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="PDF Contract Analyzer API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_jobs: dict[str, dict] = {}
_vlm_backend = None  # lazily constructed on first job, since it loads model weights


def _get_vlm_backend():
    global _vlm_backend
    if _vlm_backend is None:
        _vlm_backend = build_vlm_backend("qwen")
    return _vlm_backend


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    error: Optional[str] = None


def _run_job(job_id: str, input_path: Path, work_dir: Path) -> None:
    _jobs[job_id]["status"] = "running"
    try:
        analysis = analyze_document(input_path, work_dir, _get_vlm_backend())
        result_path = work_dir / "result.json"
        result_path.write_text(json.dumps(analysis.to_json_dict(), indent=2))
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["result_path"] = str(result_path)
        _jobs[job_id]["pdf_path"] = str(work_dir / "pdf" / f"standardized_{input_path.stem}.pdf")
    except Exception as exc:  # surfaced via GET /jobs/{id}
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(exc)


@app.post("/jobs", response_model=JobStatus)
async def create_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> JobStatus:
    job_id = uuid.uuid4().hex
    job_dir = DATA_DIR / job_id
    job_dir.mkdir(parents=True)

    input_path = job_dir / "input" / file.filename
    input_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    _jobs[job_id] = {"status": "queued", "error": None}
    background_tasks.add_task(_run_job, job_id, input_path, job_dir)

    return JobStatus(job_id=job_id, status="queued")


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    if job["status"] == "done":
        result = json.loads(Path(job["result_path"]).read_text())
        return JSONResponse({"job_id": job_id, "status": "done", "result": result})

    if job["status"] == "failed":
        return JSONResponse({"job_id": job_id, "status": "failed", "error": job["error"]})

    return JSONResponse({"job_id": job_id, "status": job["status"]})


@app.get("/jobs/{job_id}/pdf")
async def get_job_pdf(job_id: str):
    job = _jobs.get(job_id)
    if job is None or job.get("status") != "done":
        raise HTTPException(status_code=404, detail="pdf not ready")
    return FileResponse(job["pdf_path"], media_type="application/pdf")
