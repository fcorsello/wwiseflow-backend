# Migration Guide: V1 → V2

## 🎯 Cosa Cambia

La V2 introduce un **sistema modulare a grafi** con:

1. **Node Registry** - Contratti formali per ogni tipo di nodo
2. **Graph Compiler** - Validazione topologica e risoluzione dipendenze
3. **Enhanced Runner** - Idempotenza, resume, riferimenti simbolici
4. **WebSocket Streaming** - Feedback real-time durante esecuzione
5. **Extended WAAPI** - Query, setProperty, validazioni pre-flight

## 📦 Nuova Struttura File

```
wwiseflow-backend/
├── app/
│   ├── __init__.py
│   ├── pywwise_adapter.py      # V2: con lock e validazioni
│   ├── command_bus.py           # Invariato
│   ├── node_registry.py         # NUOVO: registro nodi
│   ├── graph_compiler.py        # NUOVO: toposort + validazione
│   ├── workflow_runner.py       # V1: deprecato
│   └── workflow_runner_v2.py    # NUOVO: runner evoluto
├── main.py                      # V2: nuovi endpoint
├── mcp_server.py                # Da aggiornare (vedi sotto)
├── requirements.txt
├── sample_workflow.json         # V1: funziona ancora
└── sample_workflow_v2.json      # NUOVO: con auto-wiring
```

## 🔄 Breaking Changes

### 1. Formato Workflow (Opzionale)

**V1** (ancora supportato):
```json
{
  "nodes": [
    {
      "id": "n1",
      "type": "createSound",
      "data": {
        "name": "Sound1",
        "parentPath": "/Actor-Mixer Hierarchy/..."
      }
    },
    {
      "id": "n2",
      "type": "audioImport",
      "data": {
        "sourceNode": "n1",  // ❌ Deprecato
        "filePath": "C:/file.wav"
      }
    }
  ]
}
```

**V2** (raccomandato):
```json
{
  "nodes": [
    {
      "id": "n1",
      "type": "createSound",
      "data": {
        "name": "Sound1"
      }
    },
    {
      "id": "n2",
      "type": "audioImport",
      "data": {
        "filePath": "C:/file.wav"
        // objectId risolto automaticamente da edge!
      }
    }
  ],
  "edges": [
    {
      "id": "e1-2",
      "source": "n1",
      "target": "n2"
    }
  ]
}
```

### 2. Nuovi Endpoint API

**Aggiunti:**
- `GET /api/nodes/list` - Lista nodi disponibili con metadati
- `POST /api/workflows/compile` - Compila e valida workflow
- `POST /api/workflows/validate` - Validazione semantica completa
- `WS /ws/workflow/{sessionId}` - Streaming eventi esecuzione

**Modificati:**
- `POST /api/workflows/execute` - Ora supporta `resume_from` e `force_rerun`

### 3. Risposta Execute Workflow

**V1:**
```json
{
  "ok": true,
  "results": [
    {"node": "n1", "ok": true, "result": {...}}
  ]
}
```

**V2:**
```json
{
  "ok": true,
  "executionId": "exec_abc123_2024-10-29T12:00:00",
  "timestamp": "2024-10-29T12:00:00Z",
  "results": [
    {
      "node": "n1",
      "ok": true,
      "result": {...},
      "idemKey": "a1b2c3d4",  // ✨ NUOVO: chiave idempotenza
      "idempotent": false      // ✨ NUOVO: true se saltato
    }
  ]
}
```

## 🚀 Procedura di Migrazione

### Step 1: Backup

```bash
git commit -am "Backup before V2 migration"
git tag v1-backup
```

### Step 2: Aggiorna Dipendenze

`requirements.txt` rimane invariato, nessuna nuova dipendenza!

### Step 3: Aggiungi Nuovi Moduli

Copia i nuovi file nella cartella `app/`:
- `node_registry.py`
- `graph_compiler.py`
- `workflow_runner_v2.py`

### Step 4: Aggiorna `main.py`

Sostituisci il contenuto con la versione V2 fornita.

**Opzionale**: Mantieni retrocompatibilità V1 aggiungendo:

```python
from app.workflow_runner import execute_workflow as execute_workflow_v1

@app.post("/api/workflows/execute/v1")
def execute_workflow_v1_endpoint(w: Workflow):
    """Endpoint legacy V1"""
    return execute_workflow_v1(w.flow, dry_run=w.dry_run)
```

### Step 5: Aggiorna MCP Server

```python
# mcp_server.py - Aggiungi nuovi tool

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ... tool esistenti ...
        
        Tool(
            name="compile_workflow",
            description="Compila e valida workflow prima di eseguirlo",
            input_schema={
                "type": "object",
                "properties": {
                    "flow": {"type": "object"}
                },
                "required": ["flow"]
            }
        ),
        Tool(
            name="list_node_types",
            description="Lista tutti i tipi di nodo disponibili",
            input_schema={"type": "object", "properties": {}}
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any] | None):
    arguments = arguments or {}
    
    if name == "compile_workflow":
        from app.graph_compiler import compile_workflow
        res = compile_workflow(arguments["flow"])
        return [TextContent(type="text", text=json.dumps(res, indent=2))]
    
    elif name == "list_node_types":
        from app.node_registry import get_registry
        registry = get_registry()
        nodes = [registry.get(t) for t in registry.list_types()]
        info = [{"type": n.type, "label": n.label} for n in nodes if n]
        return [TextContent(type="text", text=json.dumps(info, indent=2))]
    
    # ... altri tool ...
```

### Step 6: Test di Regressione

```bash
# Avvia backend
python main.py

# Test V1 (retrocompatibilità)
curl -X POST http://localhost:8000/api/workflows/execute \
  -H "Content-Type: application/json" \
  -d @sample_workflow.json

# Test V2 (nuove feature)
curl -X POST http://localhost:8000/api/workflows/compile \
  -H "Content-Type: application/json" \
  -d @sample_workflow_v2.json
```

## 🎨 Nuove Feature da Sfruttare

### 1. Auto-wiring Input

**Prima (V1):**
```json
{
  "nodes": [
    {"id": "n1", "type": "createSound", "data": {"name": "X"}},
    {"id": "n2", "type": "audioImport", "data": {
      "sourceNode": "n1",  // Manuale!
      "filePath": "..."
    }}
  ]
}
```

**Dopo (V2):**
```json
{
  "nodes": [
    {"id": "n1", "type": "createSound", "data": {"name": "X"}},
    {"id": "n2", "type": "audioImport", "data": {"filePath": "..."}}
  ],
  "edges": [
    {"source": "n1", "target": "n2"}  // Auto-wire!
  ]
}
```

Il compilatore risolve automaticamente `objectId` da `n1` a `n2`.

### 2. Validazione Pre-flight

```python
# Nel frontend React Flow
async function validateBeforeExecution(workflow) {
  const response = await fetch('/api/workflows/validate', {
    method: 'POST',
    body: JSON.stringify({ flow: workflow })
  });
  
  const result = await response.json();
  
  if (!result.ok) {
    // Mostra errori prima di eseguire
    result.errors.forEach(err => {
      highlightNodeError(err.nodeId, err.message);
    });
    return false;
  }
  
  return true;
}
```

### 3. Idempotenza

```python
# Esegui workflow
result1 = execute_workflow_v2(workflow)

# Re-esegui: nodi con stessi input vengono saltati
result2 = execute_workflow_v2(workflow)

# Forza riesecuzione completa
result3 = execute_workflow_v2(workflow, force_rerun=True)
```

### 4. Resume da Punto Specifico

```python
# Workflow fallisce al nodo n3
result = execute_workflow_v2(workflow)
# {"ok": false, "stopAt": "n3"}

# Aggiusta il problema, riprendi da n3
result = execute_workflow_v2(workflow, resume_from="n3")
```

### 5. WebSocket Streaming

```javascript
// Frontend React Flow
const ws = new WebSocket('ws://localhost:8000/ws/workflow/session123');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  
  if (msg.type === 'node_start') {
    highlightNode(msg.nodeId, 'running');
  }
  else if (msg.type === 'node_complete') {
    highlightNode(msg.nodeId, msg.ok ? 'success' : 'error');
  }
};

// Invia workflow per esecuzione
ws.send(JSON.stringify({ flow: workflow }));
```

## 📊 Confronto Performance

| Feature | V1 | V2 |
|---------|----|----|
| Validazione grafo | ❌ Runtime | ✅ Compile-time |
| Risoluzione dipendenze | ⚠️ Manuale | ✅ Automatica |
| Idempotenza | ❌ No | ✅ Sì |
| Resume parziale | ❌ No | ✅ Sì |
| Feedback real-time | ❌ No | ✅ WebSocket |
| Validazione file | ❌ Runtime | ✅ Pre-flight |

## 🐛 Troubleshooting

### Errore: "UNKNOWN_NODE_TYPE"

**Causa**: Il node registry non riconosce il tipo.

**Fix**: Verifica che il tipo sia registrato in `node_registry.py`:

```python
registry = get_registry()
print(registry.list_types())  # Vedi tipi disponibili
```

### Errore: "GRAPH_CYCLE"

**Causa**: Il workflow contiene cicli (n1 → n2 → n1).

**Fix**: Usa `/api/workflows/compile` per identificare i nodi coinvolti nel ciclo.

### Errore: "MISSING_INPUT"

**Causa**: Nodo richiede input non fornito né auto-wired.

**Fix**: Aggiungi edge da nodo produttore oppure valorizza manualmente in `data`.

## 📚 Risorse

- **Node Registry**: `app/node_registry.py` - Aggiungi nuovi tipi qui
- **Compiler**: `app/graph_compiler.py` - Logica toposort e validazione
- **Runner**: `app/workflow_runner_v2.py` - Esecuzione e idempotenza
- **Sample V2**: `sample_workflow_v2.json` - Esempio auto-wiring

## 🎯 Next Steps

1. **Estendi Registry**: Aggiungi nodi per query WAQL, setProperty, SoundBank generation
2. **UI React Flow**: Implementa custom nodes che rispettano contratti del registry
3. **Audit Log**: Integra logging centralizzato per compliance
4. **REAPER Bridge**: Aggiungi adapter parallelo per ReaScript

## ⚠️ Note Importanti

- **Retrocompatibilità**: Workflow V1 continuano a funzionare
- **Performance**: V2 è più veloce grazie a validazione upfront
- **Lock WAAPI**: Operazioni critiche sono thread-safe
- **Idempotenza**: Basata su hash input, non su stato Wwise

---

**Sei pronto per la migrazione? Esegui i test e fammi sapere se hai dubbi!** 🚀