import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, Optional
import asyncio
import json

from app.command_bus import CommandBus
from app.workflow_runner_v2 import execute_workflow_v2
from app.graph_compiler import compile_workflow, validate_workflow
from app.node_registry import get_registry
from app.pywwise_adapter import PyWwiseAgent

app = FastAPI(title="WwiseFlow V2")

# CORS per frontend React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In produzione: specifica domini esatti
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bus = CommandBus()

# ============================================
# MODELS
# ============================================

class Payload(BaseModel):
    payload: Dict[str, Any]

class WorkflowExecution(BaseModel):
    flow: Dict[str, Any]
    dry_run: bool = False
    resume_from: Optional[str] = None
    force_rerun: bool = False


# ============================================
# HEALTH & INFO
# ============================================

@app.get("/health")
def health():
    return {"ok": True, "version": "2.0"}

@app.get("/health/wwise")
def wwise_health():
    """Verifica connessione WAAPI"""
    try:
        with PyWwiseAgent() as agent:
            info = agent.ak.wwise.core.get_info()
            return {
                "ok": True,
                "connected": True,
                "wwise": {
                    "version": info.get("displayName", "unknown"),
                    "platform": info.get("platform", {}).get("basePlatform", "unknown")
                }
            }
    except Exception as e:
        return {
            "ok": False,
            "connected": False,
            "error": str(e)
        }

@app.get("/api/nodes/list")
def list_node_types():
    """Lista tutti i tipi di nodo disponibili con metadati"""
    registry = get_registry()
    
    nodes = []
    for node_type in registry.list_types():
        spec = registry.get(node_type)
        if spec:
            nodes.append({
                "type": spec.type,
                "label": spec.label,
                "description": spec.description,
                "category": spec.category,
                "inputs": {
                    "required": spec.required,
                    "optional": spec.optional
                },
                "outputs": spec.outputs
            })
    
    return {"ok": True, "nodes": nodes}


# ============================================
# WORKFLOW OPERATIONS
# ============================================

@app.post("/api/workflows/compile")
def compile_workflow_endpoint(w: WorkflowExecution):
    """
    Compila workflow e restituisce piano di esecuzione.
    Utile per validazione pre-flight e anteprima.
    """
    result = compile_workflow(w.flow)
    return result

@app.post("/api/workflows/validate")
def validate_workflow_endpoint(w: WorkflowExecution):
    """
    Validazione completa: compilazione + controlli semantici
    (file esistono, parent validi, etc)
    """
    result = validate_workflow(w.flow)
    return result

@app.post("/api/workflows/execute")
def execute_workflow_endpoint(w: WorkflowExecution):
    """
    Esegue workflow compilato con gestione avanzata.
    Supporta dry_run, resume_from, idempotenza.
    """
    result = execute_workflow_v2(
        w.flow,
        dry_run=w.dry_run,
        resume_from=w.resume_from,
        force_rerun=w.force_rerun
    )
    return result


# ============================================
# WEBSOCKET STREAMING
# ============================================

class ConnectionManager:
    """Gestisce connessioni WebSocket attive"""
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket
    
    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
    
    async def send_event(self, session_id: str, event: Dict):
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            try:
                await websocket.send_json(event)
            except:
                self.disconnect(session_id)

manager = ConnectionManager()

@app.websocket("/ws/workflow/{session_id}")
async def workflow_stream(websocket: WebSocket, session_id: str):
    """
    WebSocket per streaming eventi durante esecuzione workflow.
    
    Eventi emessi:
    - {"type": "workflow_start", "executionId": "..."}
    - {"type": "node_start", "nodeId": "n1"}
    - {"type": "node_complete", "nodeId": "n1", "ok": true, "result": {...}}
    - {"type": "workflow_complete", "ok": true}
    - {"type": "workflow_error", "error": "...", "nodeId": "..."}
    """
    await manager.connect(session_id, websocket)
    
    try:
        while True:
            # Mantieni connessione aperta
            data = await websocket.receive_text()
            
            # Se riceve un workflow, eseguilo con streaming
            if data:
                try:
                    payload = json.loads(data)
                    flow = payload.get("flow")
                    
                    if flow:
                        await _execute_with_streaming(session_id, flow)
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid JSON"
                    })
    
    except WebSocketDisconnect:
        manager.disconnect(session_id)

async def _execute_with_streaming(session_id: str, flow: Dict):
    """Esegue workflow emettendo eventi via WebSocket"""
    
    # Compila
    await manager.send_event(session_id, {
        "type": "compilation_start"
    })
    
    compilation = compile_workflow(flow)
    
    if not compilation["ok"]:
        await manager.send_event(session_id, {
            "type": "compilation_error",
            "errors": compilation["errors"]
        })
        return
    
    await manager.send_event(session_id, {
        "type": "compilation_complete",
        "plan": compilation["plan"]
    })
    
    # Esegui con eventi
    plan = compilation["plan"]
    context = {}
    
    await manager.send_event(session_id, {
        "type": "execution_start",
        "nodeCount": len(plan)
    })
    
    for step in plan:
        node_id = step["nodeId"]
        
        await manager.send_event(session_id, {
            "type": "node_start",
            "nodeId": node_id,
            "type": step["type"]
        })
        
        # Simula esecuzione (in realtà chiameresti il runner qui)
        await asyncio.sleep(0.5)  # Simula latenza
        
        # TODO: integrare con runner reale
        result = {"ok": True, "data": {"id": f"obj_{node_id}"}}
        
        await manager.send_event(session_id, {
            "type": "node_complete",
            "nodeId": node_id,
            "ok": result["ok"],
            "result": result
        })
        
        if not result["ok"]:
            await manager.send_event(session_id, {
                "type": "execution_error",
                "nodeId": node_id,
                "error": result.get("error")
            })
            return
    
    await manager.send_event(session_id, {
        "type": "execution_complete",
        "ok": True
    })


# ============================================
# ATOMIC COMMANDS (backward compatibility)
# ============================================

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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)