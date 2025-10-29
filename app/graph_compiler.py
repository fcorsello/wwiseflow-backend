"""
Graph Compiler: compila un workflow React Flow in un piano eseguibile.

Fasi:
1. Indicizza nodi ed edge
2. Verifica cicli (toposort)
3. Risolve dipendenze automatiche (edge → $from/$output)
4. Valida input obbligatori
5. Restituisce piano ordinato o errori di compilazione
"""
from typing import Dict, Any, List, Set, Optional, Tuple
from collections import defaultdict, deque
from .node_registry import get_registry


class CompilationError(Exception):
    """Errore durante la compilazione del workflow"""
    def __init__(self, code: str, message: str, node_id: Optional[str] = None):
        self.code = code
        self.message = message
        self.node_id = node_id
        super().__init__(f"[{code}] {message}" + (f" (nodo: {node_id})" if node_id else ""))


def compile_workflow(flow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compila un workflow React Flow in un piano eseguibile.
    
    Input: {nodes: [...], edges: [...]}
    Output: {
        ok: bool,
        plan: List[Dict],  # Sequenza ordinata topologicamente
        errors: List[Dict],  # Errori di compilazione
        warnings: List[Dict]  # Warning non bloccanti
    }
    """
    try:
        nodes = flow.get("nodes", [])
        edges = flow.get("edges", [])
        
        # 1. Indicizza nodi
        node_map = {n["id"]: n for n in nodes}
        
        # 2. Costruisci grafo delle dipendenze
        graph = defaultdict(list)  # node_id -> [dependent_node_ids]
        in_degree = defaultdict(int)
        
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            
            if not source or not target:
                raise CompilationError(
                    "INVALID_EDGE",
                    f"Edge con source/target mancante: {edge}"
                )
            
            if source not in node_map:
                raise CompilationError(
                    "UNKNOWN_NODE",
                    f"Source node non trovato: {source}",
                    source
                )
            
            if target not in node_map:
                raise CompilationError(
                    "UNKNOWN_NODE",
                    f"Target node non trovato: {target}",
                    target
                )
            
            graph[source].append(target)
            in_degree[target] += 1
        
        # Inizializza in_degree per tutti i nodi
        for node in nodes:
            if node["id"] not in in_degree:
                in_degree[node["id"]] = 0
        
        # 3. Toposort (Kahn's algorithm)
        ordered = []
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        
        while queue:
            current = queue.popleft()
            ordered.append(current)
            
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # 4. Verifica cicli
        if len(ordered) != len(nodes):
            # Ci sono cicli
            remaining = set(node_map.keys()) - set(ordered)
            raise CompilationError(
                "GRAPH_CYCLE",
                f"Il grafo contiene cicli. Nodi coinvolti: {', '.join(remaining)}"
            )
        
        # 5. Costruisci piano con risoluzione input
        registry = get_registry()
        plan = []
        warnings = []
        producers = _build_output_map(ordered, node_map, registry)
        
        for node_id in ordered:
            node = node_map[node_id]
            node_type = node.get("type")
            node_data = dict(node.get("data", {}))
            
            # Recupera specifica dal registry
            spec = registry.get(node_type)
            if not spec:
                raise CompilationError(
                    "UNKNOWN_NODE_TYPE",
                    f"Tipo nodo sconosciuto: {node_type}",
                    node_id
                )
            
            # Risolvi input automatici da edge
            incoming_edges = [e for e in edges if e.get("target") == node_id]
            resolved_data = _resolve_inputs(
                node_id, 
                node_data, 
                incoming_edges, 
                producers, 
                spec
            )
            
            # Valida input obbligatori
            validation = registry.validate_node_data(node_type, resolved_data)
            if not validation["valid"]:
                missing_fields = validation["missing"]
                # Cerca da quali nodi potrebbero arrivare questi input
                suggestions = _suggest_connections(missing_fields, producers, node_id)
                
                error_msg = f"Input mancanti per {node_type}: {', '.join(missing_fields)}"
                if suggestions:
                    error_msg += f"\nSuggerimento: collega {node_id} con uno di questi nodi: {', '.join(suggestions)}"
                
                raise CompilationError(
                    "MISSING_INPUT",
                    error_msg,
                    node_id
                )
            
            # Aggiungi al piano
            plan.append({
                "nodeId": node_id,
                "type": node_type,
                "data": resolved_data,
                "spec": {
                    "required": spec.required,
                    "outputs": spec.outputs
                }
            })
        
        return {
            "ok": True,
            "plan": plan,
            "errors": [],
            "warnings": warnings
        }
    
    except CompilationError as e:
        return {
            "ok": False,
            "plan": [],
            "errors": [{
                "code": e.code,
                "message": e.message,
                "nodeId": e.node_id
            }],
            "warnings": []
        }
    except Exception as e:
        return {
            "ok": False,
            "plan": [],
            "errors": [{
                "code": "COMPILATION_FAILED",
                "message": str(e),
                "nodeId": None
            }],
            "warnings": []
        }


def _build_output_map(
    ordered: List[str], 
    node_map: Dict, 
    registry
) -> Dict[str, Set[str]]:
    """
    Mappa: output_name -> {node_ids che lo producono}
    Es: {"objectId": {"n1", "n2"}}
    """
    producers = defaultdict(set)
    
    for node_id in ordered:
        node = node_map[node_id]
        spec = registry.get(node.get("type"))
        if spec:
            for output in spec.outputs:
                producers[output].add(node_id)
    
    return producers


def _resolve_inputs(
    node_id: str,
    node_data: Dict,
    incoming_edges: List[Dict],
    producers: Dict[str, Set[str]],
    spec
) -> Dict:
    """
    Risolve automaticamente input da edge.
    Se un input obbligatorio non è in node_data ma c'è un edge
    da un nodo che produce quell'output, crea un $from reference.
    """
    resolved = dict(node_data)
    
    for required_field in spec.required:
        # Se già valorizzato, skip
        if required_field in resolved and resolved[required_field]:
            continue
        
        # Cerca se un predecessore produce questo field
        for edge in incoming_edges:
            source_id = edge.get("source")
            
            # Il source produce questo field?
            if source_id in producers.get(required_field, set()):
                # Auto-wire con reference simbolica
                resolved[required_field] = f"$from:{source_id}:$output:{required_field}"
                break
    
    return resolved


def _suggest_connections(
    missing_fields: List[str],
    producers: Dict[str, Set[str]],
    current_node: str
) -> List[str]:
    """Suggerisce nodi da collegare per soddisfare input mancanti"""
    suggestions = set()
    
    for field in missing_fields:
        if field in producers:
            suggestions.update(producers[field])
    
    # Rimuovi il nodo corrente (non può collegarsi a se stesso)
    suggestions.discard(current_node)
    
    return list(suggestions)


def validate_workflow(flow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrapper di compile_workflow per validazione pre-flight.
    Aggiunge controlli semantici (file esistono, etc).
    """
    compilation = compile_workflow(flow)
    
    if not compilation["ok"]:
        return compilation
    
    # Controlli semantici aggiuntivi
    import os
    semantic_errors = []
    
    for step in compilation["plan"]:
        node_id = step["nodeId"]
        node_type = step["type"]
        data = step["data"]
        
        # Verifica esistenza file per audioImport
        if node_type == "audioImport":
            filepath = data.get("filePath", "")
            # Skip riferimenti simbolici
            if not filepath.startswith("$from:") and filepath:
                if not os.path.exists(filepath):
                    semantic_errors.append({
                        "code": "FILE_NOT_FOUND",
                        "message": f"File non trovato: {filepath}",
                        "nodeId": node_id
                    })
        
        # TODO: verifica parent esistono in Wwise (richiede query WAAPI)
        # TODO: verifica bus path validi
    
    if semantic_errors:
        return {
            "ok": False,
            "plan": compilation["plan"],
            "errors": semantic_errors,
            "warnings": compilation["warnings"]
        }
    
    return compilation