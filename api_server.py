from __future__ import annotations

import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from validation_service import run_validation, system_info


app = FastAPI(title="TraceWise API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/bootstrap")
def bootstrap():
    return system_info()


@app.post("/api/validate")
async def validate(
    candidate_file: UploadFile = File(...),
    reference_file: UploadFile | None = File(default=None),
    rules: str = Form("{}"),
    tolerances: str = Form("{}"),
    use_bundled_reference: str = Form("false"),
    include_ai: str = Form("false"),
    ai_model: str = Form(""),
):
    try:
        rules_payload = json.loads(rules or "{}")
        tolerances_payload = json.loads(tolerances or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc.msg}") from exc

    try:
        candidate_payload = await candidate_file.read()
        reference_payload = await reference_file.read() if reference_file else None
        result = run_validation(
            candidate_name=candidate_file.filename or "candidate.kicad_pcb",
            candidate_payload=candidate_payload,
            rules=rules_payload,
            tolerances=tolerances_payload,
            reference_name=reference_file.filename if reference_file else None,
            reference_payload=reference_payload,
            use_bundled_reference=use_bundled_reference.lower() == "true",
            include_ai=include_ai.lower() == "true",
            ai_model=ai_model or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Validation failed: {exc}") from exc

    return result
