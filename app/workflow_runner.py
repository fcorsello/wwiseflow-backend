"""
Workflow runner con protezioni:
- valida dipendenze (sourceNode) prima di leggere dal contesto
- interrompe il flusso al primo errore senza eccezioni
- supporta dry_run
Nodi supportati:
  - createSound { name, parentPath? }
  - audioImport { objectId? | sourceNode, filePath, language? }
  - setReference { objectId? | sourceNode, reference='OutputBus', valuePath }
  - projectSave {}
"""
from typing import Dict, Any, List
from .command_bus import CommandBus

def _extract_id_from_data(data: Any) -> str | None:
    """Accetta sia dict che oggetti con attributo .id."""
    if data is None:
        return None
    if isinstance(data, dict):
        return data.get("id")
    return getattr(data, "id", None)

def execute_workflow(flow: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    bus = CommandBus()
    ctx: Dict[str, Dict[str, str]] = {}   # nodeId -> {"objectId": "..."}
    results: List[Dict[str, Any]] = []
    nodes = flow.get("nodes", [])

    def fail(node_id: str, code: str, msg: str):
        results.append({"node": node_id, "ok": False, "code": code, "error": msg})

    for node in nodes:
        nid = node.get("id")
        ntype = node.get("type")
        data = dict(node.get("data", {}))  # copia difensiva

        if not nid or not ntype:
            results.append({"node": nid or "<unknown>", "ok": False, "code": "INVALID_NODE", "error": "Nodo senza id o type"})
            continue

        if dry_run:
            results.append({"node": nid, "ok": True, "dryRun": True, "type": ntype, "data": data})
            continue

        # helper per recuperare un objectId da data o da sourceNode
        def ensure_object_id() -> str | None:
            if "objectId" in data and data["objectId"]:
                return data["objectId"]
            src = data.get("sourceNode")
            if not src:
                return None
            ref = ctx.get(src)
            if not ref:
                return None
            return ref.get("objectId")

        if ntype == "createSound":
            res = bus.create_sound(data)
            results.append({"node": nid, "result": res})
            if res.get("ok"):
                oid = _extract_id_from_data(res.get("data"))
                if oid:
                    ctx[nid] = {"objectId": oid}
                else:
                    fail(nid, "MISSING_ID", "createSound: nessun id ritornato dal backend")
                    return {"ok": False, "stopped": True, "stopAt": nid, "results": results}
            else:
                fail(nid, res.get("code", "STEP_FAILED"), res.get("error", "createSound fallita"))
                return {"ok": False, "stopped": True, "stopAt": nid, "results": results}

        elif ntype == "audioImport":
            obj = ensure_object_id()
            if not obj:
                fail(nid, "MISSING_DEPENDENCY", "audioImport richiede objectId o sourceNode valido")
                return {"ok": False, "stopped": True, "stopAt": nid, "results": results}
            data["objectId"] = obj
            res = bus.audio_import(data)
            results.append({"node": nid, "result": res})
            if not res.get("ok"):
                fail(nid, res.get("code", "STEP_FAILED"), res.get("error", "audioImport fallita"))
                return {"ok": False, "stopped": True, "stopAt": nid, "results": results}

        elif ntype == "setReference":
            if data.get("reference") != "OutputBus":
                fail(nid, "UNSUPPORTED_REFERENCE", "Solo OutputBus è supportato in questo sample")
                return {"ok": False, "stopped": True, "stopAt": nid, "results": results}
            obj = ensure_object_id()
            if not obj:
                fail(nid, "MISSING_DEPENDENCY", "setReference richiede objectId o sourceNode valido")
                return {"ok": False, "stopped": True, "stopAt": nid, "results": results}
            res = bus.set_output_bus({"objectId": obj, "busPath": data.get("valuePath")})
            results.append({"node": nid, "result": res})
            if not res.get("ok"):
                fail(nid, res.get("code", "STEP_FAILED"), res.get("error", "setReference fallita"))
                return {"ok": False, "stopped": True, "stopAt": nid, "results": results}

        elif ntype == "projectSave":
            res = bus.project_save({})
            results.append({"node": nid, "result": res})
            if not res.get("ok"):
                fail(nid, res.get("code", "STEP_FAILED"), res.get("error", "projectSave fallita"))
                return {"ok": False, "stopped": True, "stopAt": nid, "results": results}

        else:
            fail(nid, "UNKNOWN_NODE", f"Tipo nodo non supportato: {ntype}")
            return {"ok": False, "stopped": True, "stopAt": nid, "results": results}

    return {"ok": True, "results": results}
