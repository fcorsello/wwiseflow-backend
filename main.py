import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
from app.command_bus import CommandBus
from app.workflow_runner import execute_workflow

app = FastAPI(title="WwiseFlow")
bus = CommandBus()

class Payload(BaseModel):
    payload: Dict[str, Any]

class Workflow(BaseModel):
    flow: Dict[str, Any]
    dry_run: bool = False

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/wwise/create-sound")
def create_sound(p: Payload):
    res = bus.create_sound(p.payload)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error"))
    return res

@app.post("/api/wwise/set-output-bus")
def set_output_bus(p: Payload):
    res = bus.set_output_bus(p.payload)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error"))
    return res

@app.post("/api/wwise/audio-import")
def audio_import(p: Payload):
    res = bus.audio_import(p.payload)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error"))
    return res

@app.post("/api/wwise/project-save")
def project_save(p: Payload):
    res = bus.project_save(p.payload)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error"))
    return res

@app.post("/api/workflows/execute")
def run_workflow(w: Workflow):
    res = execute_workflow(w.flow, dry_run=w.dry_run)
    return res

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
