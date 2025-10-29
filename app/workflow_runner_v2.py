"""
Workflow Runner V2: esegue piano compilato con idempotenza e risoluzione simbolica.

Features:
- Risolve $from:nodeId:$output:field da contesto
- Idempotenza: salta step già eseguiti con stessi input
- Interrompe al primo errore
- Supporta dry_run per anteprima
- Esporta chiavi di idempotenza nei risultati
"""
from typing import Dict, Any, List, Optional
import hashlib
import json
from datetime import datetime
from .command_bus import CommandBus
from .graph_compiler import compile_workflow
from .node_registry import get_registry


def execute_workflow_v2(
    flow: Dict[str, Any],
    dry_run: bool = False,
    resume_from: Optional[str] = None,
    force_rerun: bool = False
) -> Dict[str, Any]:
    """
    Esegue workflow compilato con gestione avanzata.
    
    Args:
        flow: Workflow React Flow format
        dry_run: Se True, restituisce piano senza eseguire
        resume_from: Riprendi da questo nodeId (skip precedenti)
        force_rerun: Forza riesecuzione anche se idempotente
    
    Returns:
        {
            ok: bool,
            results: List[Dict],  # Risultati per nodo
            stopped: bool,
            stopAt: str,
            executionId: str,
            timestamp: str
        }
    """
    # 1. Compila workflow
    compilation = compile_workflow(flow)
    
    if not compilation["ok"]:
        return {
            "ok": False,
            "stopped": True,
            "stopAt": None,
            "errors": compilation["errors"],
            "results": []
        }
    
    plan = compilation["plan"]
    
    # Genera execution ID unico
    execution_id = _generate_execution_id(flow)
    
    # Se dry_run, restituisci solo il piano
    if dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "plan": plan,
            "results": [],
            "executionId": execution_id,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    # 2. Esegui piano
    bus = CommandBus()
    registry = get_registry()
    context: Dict[str, Dict[str, Any]] = {}  # nodeId -> {output_name: value}
    results: List[Dict] = []
    memo: Dict[str, str] = {}  # idem_key -> result (per idempotenza)
    
    # Flag resume
    skip_until = resume_from is not None
    
    for step in plan:
        node_id = step["nodeId"]
        node_type = step["type"]
        raw_data = step["data"]
        
        # Resume logic
        if skip_until:
            if node_id == resume_from:
                skip_until = False
            else:
                results.append({
                    "node": node_id,
                    "ok": True,
                    "skipped": True,
                    "reason": "resume_from"
                })
                continue
        
        # 3. Risolvi riferimenti simbolici $from:...:$output:...
        try:
            resolved_data = _resolve_symbolic_refs(raw_data, context)
        except KeyError as e:
            return _fail_result(
                results, 
                node_id, 
                "RESOLUTION_FAILED", 
                f"Impossibile risolvere riferimento: {str(e)}"
            )
        
        # 4. Calcola chiave di idempotenza
        idem_key = _idempotency_key(node_id, node_type, resolved_data)
        
        # 5. Verifica se già eseguito (idempotenza)
        if not force_rerun and idem_key in memo:
            cached_result = memo[idem_key]
            results.append({
                "node": node_id,
                "ok": True,
                "idempotent": True,
                "idemKey": idem_key,
                "cachedResult": cached_result
            })
            # Usa risultato cached per contesto
            if cached_result.get("ok"):
                _export_outputs_to_context(
                    node_id, 
                    cached_result.get("data", {}), 
                    step["spec"]["outputs"], 
                    context
                )
            continue
        
        # 6. Esegui nodo
        spec = registry.get(node_type)
        if not spec:
            return _fail_result(
                results,
                node_id,
                "UNKNOWN_NODE_TYPE",
                f"Tipo nodo non supportato: {node_type}"
            )
        
        result = spec.run(resolved_data, bus)
        
        # 7. Memorizza risultato
        memo[idem_key] = result
        
        results.append({
            "node": node_id,
            "ok": result.get("ok", False),
            "result": result,
            "idemKey": idem_key,
            "data": resolved_data  # Dati effettivamente usati
        })
        
        # 8. Interrompi se errore
        if not result.get("ok"):
            return {
                "ok": False,
                "stopped": True,
                "stopAt": node_id,
                "results": results,
                "executionId": execution_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # 9. Esporta output nel contesto
        _export_outputs_to_context(
            node_id, 
            result.get("data", {}), 
            step["spec"]["outputs"], 
            context
        )
    
    return {
        "ok": True,
        "results": results,
        "executionId": execution_id,
        "timestamp": datetime.utcnow().isoformat()
    }


def _resolve_symbolic_refs(data: Dict, context: Dict) -> Dict:
    """
    Risolve riferimenti simbolici nel formato:
    "$from:n1:$output:objectId" -> context["n1"]["objectId"]
    
    Supporta anche template semplici:
    "MySound_${timestamp}" -> "MySound_20241029123456"
    """
    resolved = {}
    
    for key, value in data.items():
        if isinstance(value, str) and value.startswith("$from:"):
            # Parse: $from:nodeId:$output:fieldName
            parts = value.split(":")
            if len(parts) != 4 or parts[2] != "$output":
                raise KeyError(f"Formato $from invalido: {value}")
            
            source_node = parts[1]
            field_name = parts[3]
            
            if source_node not in context:
                raise KeyError(f"Nodo source non trovato nel contesto: {source_node}")
            
            if field_name not in context[source_node]:
                raise KeyError(f"Output non trovato: {field_name} da nodo {source_node}")
            
            resolved[key] = context[source_node][field_name]
        
        elif isinstance(value, str) and "${timestamp}" in value:
            # Template timestamp
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            resolved[key] = value.replace("${timestamp}", timestamp)
        
        elif isinstance(value, str) and "${HHmmss}" in value:
            # Template time-only
            time_str = datetime.now().strftime("%H%M%S")
            resolved[key] = value.replace("${HHmmss}", time_str)
        
        else:
            resolved[key] = value
    
    return resolved


def _export_outputs_to_context(
    node_id: str,
    result_data: Any,
    output_fields: List[str],
    context: Dict
):
    """
    Estrae output dal result e li mette nel contesto.
    Es: result_data = {"id": "123", "name": "Sound"}
        output_fields = ["objectId"]
        → context["n1"] = {"objectId": "123"}
    """
    if node_id not in context:
        context[node_id] = {}
    
    # result_data può essere dict o oggetto con attributi
    if isinstance(result_data, dict):
        for field in output_fields:
            # Mapping speciale: objectId <- id
            if field == "objectId" and "id" in result_data:
                context[node_id][field] = result_data["id"]
            elif field in result_data:
                context[node_id][field] = result_data[field]
    else:
        # Oggetto con attributi
        for field in output_fields:
            if field == "objectId" and hasattr(result_data, "id"):
                context[node_id][field] = getattr(result_data, "id")
            elif hasattr(result_data, field):
                context[node_id][field] = getattr(result_data, field)


def _idempotency_key(node_id: str, node_type: str, data: Dict) -> str:
    """
    Genera chiave di idempotenza basata su:
    - node_id
    - node_type
    - hash dei dati (ordinato)
    
    Se eseguo due volte lo stesso nodo con gli stessi input,
    la chiave sarà identica.
    """
    payload = {
        "nodeId": node_id,
        "type": node_type,
        "data": _stable_dict(data)
    }
    
    json_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]


def _stable_dict(d: Dict) -> Dict:
    """Rimuove campi non deterministici per idempotenza"""
    # Filtra campi che cambiano ad ogni run ma non sono semanticamente rilevanti
    ignore_keys = {"timestamp", "executionId", "_internal"}
    return {k: v for k, v in d.items() if k not in ignore_keys}


def _generate_execution_id(flow: Dict) -> str:
    """Genera ID unico per questa esecuzione"""
    timestamp = datetime.utcnow().isoformat()
    flow_hash = hashlib.md5(json.dumps(flow, sort_keys=True).encode()).hexdigest()[:8]
    return f"exec_{flow_hash}_{timestamp}"


def _fail_result(results: List, node_id: str, code: str, message: str) -> Dict:
    """Helper per risultato di fallimento"""
    results.append({
        "node": node_id,
        "ok": False,
        "code": code,
        "error": message
    })
    
    return {
        "ok": False,
        "stopped": True,
        "stopAt": node_id,
        "results": results
    }