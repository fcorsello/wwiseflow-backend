"""
Command Bus: valida DTO e inoltra all'adapter PyWwise.
Questa versione intercetta SEMPRE le eccezioni (es. WAAPI down) e
normalizza res.data in dict per evitare AttributeError a valle.
"""
from typing import Dict, Any
from .pywwise_adapter import PyWwiseAgent, WwiseResult

def _exc(e: Exception, code: str = "WAAPI_CONNECT_FAILED") -> Dict[str, Any]:
    return {"ok": False, "error": str(e), "code": code}

def _to_plain(obj: Any) -> Any:
    """Converte WwiseObjectInfo (o oggetti simili) in dict minimale."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    # prova con attributi comuni di WwiseObjectInfo
    plain = {}
    for attr in ("id", "name", "type", "path"):
        if hasattr(obj, attr):
            plain[attr] = getattr(obj, attr)
    if plain:
        return plain
    # fallback: prova __dict__ oppure repr
    try:
        d = dict(obj.__dict__)
        # toglie dettagli rumorosi se presenti
        for k in list(d.keys()):
            if k.startswith("_"):
                d.pop(k, None)
        return d
    except Exception:
        return {"repr": repr(obj)}

def _normalize(res: WwiseResult) -> Dict[str, Any]:
    out = {"ok": res.ok}
    if res.error:
        out["error"] = res.error
    if hasattr(res, "code") and getattr(res, "code") is not None:
        out["code"] = getattr(res, "code")
    if res.data is not None:
        out["data"] = _to_plain(res.data)
    return out

class CommandBus:
    def __init__(self):
        pass

    def create_sound(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = payload.get("name") or "Sound"
        parent = payload.get("parentPath")
        try:
            with PyWwiseAgent() as agent:
                res: WwiseResult = agent.create_sound(name=name, parent_path=parent)
                return _normalize(res)
        except Exception as e:
            return _exc(e)

    def set_output_bus(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        obj = payload.get("objectId")
        bus = payload.get("busPath")
        if not obj or not bus:
            return {"ok": False, "error": "objectId e busPath sono obbligatori", "code": "INVALID_INPUT"}
        try:
            with PyWwiseAgent() as agent:
                res: WwiseResult = agent.set_output_bus(obj, bus)
                return _normalize(res)
        except Exception as e:
            return _exc(e)

    def audio_import(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        obj = payload.get("objectId")
        path = payload.get("filePath")
        lang = payload.get("language", "SFX")
        if not obj or not path:
            return {"ok": False, "error": "objectId e filePath sono obbligatori", "code": "INVALID_INPUT"}
        try:
            with PyWwiseAgent() as agent:
                res: WwiseResult = agent.audio_import(obj, path, lang)
                return _normalize(res)
        except Exception as e:
            return _exc(e)

    def project_save(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with PyWwiseAgent() as agent:
                res: WwiseResult = agent.project_save()
                return _normalize(res)
        except Exception as e:
            return _exc(e)
