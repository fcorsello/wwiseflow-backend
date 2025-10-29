# WwiseFlow Architecture V2 - Visione Completa

## 🎯 Filosofia di Design

**Principio Cardine**: *Un solo motore, molte interfacce*

```
Interfacce Diverse → Command Bus Unico → WAAPI Wwise
   (React Flow)          (Validazione)      (Esecuzione)
   (MCP/Cline)           (Routing)
   (REST API)            (Normalizzazione)
```

---

## 🏗️ Architettura Stratificata

### Layer 1: Ingresso (Multiple Facades)

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  React Flow UI  │  │   MCP Client    │  │   REST Client   │
│   (Frontend)    │  │    (Cline)      │  │   (External)    │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                     │                     │
         │ HTTP POST           │ stdio               │ HTTP POST
         │ /workflows/execute  │ call_tool           │ /wwise/create
         │                     │                     │
         └─────────────────────┴─────────────────────┘
                               │
                               ▼
```

**Caratteristiche**:
- **Zero duplicazione logica** - Tutte le interfacce usano lo stesso bus
- **Coerenza garantita** - Validazione, errori e log identici
- **Estensibilità** - Aggiungi nuove interfacce senza toccare il core

---

### Layer 2: Orchestrazione (Workflow Engine)

```
                    ┌──────────────────────────┐
                    │   WORKFLOW COMPILER      │
                    │                          │
                    │  1. Parse nodes/edges    │
                    │  2. Topological sort     │
                    │  3. Detect cycles        │
                    │  4. Validate inputs      │
                    │  5. Auto-wire deps       │
                    └──────────┬───────────────┘
                               │
                               │ Compiled Plan
                               ▼
                    ┌──────────────────────────┐
                    │   WORKFLOW RUNNER V2     │
                    │                          │
                    │  1. Resolve $from refs   │
                    │  2. Check idempotency    │
                    │  3. Execute steps        │
                    │  4. Update context       │
                    │  5. Handle errors        │
                    └──────────┬───────────────┘
                               │
                               │ Commands
                               ▼
```

**Responsabilità**:
- **Compilatore**: Trasforma grafo React Flow in piano eseguibile
- **Runner**: Esegue piano rispettando dipendenze e idempotenza

**Flow Dati**:
```
Workflow JSON → Compile → Plan → Execute → Results
     ↓              ↓        ↓       ↓         ↓
  Validazione   Toposort  Context  WAAPI   Feedback
```

---

### Layer 3: Business Logic (Command Bus)

```
                    ┌──────────────────────────┐
                    │     COMMAND BUS          │
                    │                          │
                    │  • Validates payloads    │
                    │  • Normalizes responses  │
                    │  • Catches exceptions    │
                    │  • Returns uniform DTOs  │
                    │                          │
                    │  Commands:               │
                    │  ├─ create_sound()       │
                    │  ├─ audio_import()       │
                    │  ├─ set_output_bus()     │
                    │  ├─ set_property()       │
                    │  ├─ query_waql()         │
                    │  └─ project_save()       │
                    └──────────┬───────────────┘
                               │
                               │ Adapter Calls
                               ▼
```

**Contratto Input/Output**:
```python
# Input: Dict[str, Any]
{
  "name": "MySound",
  "parentPath": "/Actor-Mixer/..."
}

# Output: Dict[str, Any]
{
  "ok": True,
  "data": {"id": "...", "name": "...", "path": "..."},
  "error": None,
  "code": None
}
```

**Garanzie**:
- ✅ Nessuna eccezione non gestita raggiunge l'API
- ✅ Risposta sempre in formato standard
- ✅ Codici errore semantici (`INVALID_INPUT`, `FILE_NOT_FOUND`, etc)

---

### Layer 4: WAAPI Integration (Adapter)

```
                    ┌──────────────────────────┐
                    │   PYWWISE ADAPTER        │
                    │                          │
                    │  • Manages WAAPI conn    │
                    │  • Event loop handling   │
                    │  • Thread-safe (RLock)   │
                    │  • Pre-flight checks     │
                    │  • ID resolution         │
                    │                          │
                    │  with _WAAPI_LOCK:       │
                    │    ak.wwise.core....     │
                    └──────────┬───────────────┘
                               │
                               │ WAAPI Protocol
                               ▼
                    ┌──────────────────────────┐
                    │   WWISE AUTHORING        │
                    │   (localhost:8080)       │
                    └──────────────────────────┘
```

**Problemi Risolti**:
- 🔒 **Concorrenza**: `RLock` serializza operazioni critiche
- 🔄 **Event Loop**: Gestione automatica in thread worker FastAPI
- 📁 **File Validation**: Check esistenza prima di import
- 🆔 **ID Resolution**: Converte `id:xxx` in path stabile

---

## 🔄 Flusso Esecuzione Completo

### Caso d'Uso: "Import WAV in nuovo Sound"

```
┌─────────────────────────────────────────────────────────────┐
│ 1. FRONTEND - Crea workflow                                 │
│                                                              │
│   nodes: [createSound, audioImport, setOutputBus, save]    │
│   edges: [n1→n2, n1→n3, n3→n4]                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ HTTP POST /workflows/execute
┌─────────────────────────────────────────────────────────────┐
│ 2. COMPILER - Valida e prepara piano                        │
│                                                              │
│   ✓ Toposort: n1 → n2, n3 → n4                            │
│   ✓ No cycles detected                                      │
│   ✓ Auto-wire: n2.objectId ← n1.objectId                  │
│   ✓ All required inputs satisfied                           │
│                                                              │
│   Plan: [                                                    │
│     {nodeId: n1, type: createSound, data: {...}},          │
│     {nodeId: n2, type: audioImport, data: {                │
│       objectId: "$from:n1:$output:objectId",               │
│       filePath: "C:/temp/sound.wav"                         │
│     }},                                                      │
│     ...                                                      │
│   ]                                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. RUNNER - Esegue piano                                    │
│                                                              │
│   Step 1: Execute n1 (createSound)                          │
│   ├─ Resolve data: {name: "Sound1", parentPath: "/..."}   │
│   ├─ Check idempotency: MISS (primo run)                   │
│   ├─ Call: bus.create_sound(...)                           │
│   ├─ Result: {ok: true, data: {id: "obj_123"}}            │
│   └─ Update context: {n1: {objectId: "obj_123"}}          │
│                                                              │
│   Step 2: Execute n2 (audioImport)                          │
│   ├─ Resolve refs: $from:n1 → objectId: "obj_123"         │
│   ├─ Check idempotency: MISS                               │
│   ├─ Call: bus.audio_import({                              │
│   │     objectId: "obj_123",                                │
│   │     filePath: "C:/temp/sound.wav"                       │
│   │   })                                                     │
│   └─ Result: {ok: true}                                    │
│                                                              │
│   Step 3: Execute n3 (setOutputBus)                         │
│   ├─ Resolve refs: $from:n1 → objectId: "obj_123"         │
│   └─ Call: bus.set_output_bus(...)                         │
│                                                              │
│   Step 4: Execute n4 (projectSave)                          │
│   └─ Call: bus.project_save()                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. COMMAND BUS - Per ogni comando                           │
│                                                              │
│   with PyWwiseAgent() as agent:                             │
│     result = agent.create_sound(...)                        │
│     return _normalize(result)                               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. ADAPTER - Esegue su WAAPI                                │
│                                                              │
│   with _WAAPI_LOCK:                                         │
│     info = ak.wwise.core.object.create(                     │
│       "Sound1",                                              │
│       EObjectType.SOUND,                                     │
│       parent,                                                │
│       ENameConflictStrategy.RENAME                           │
│     )                                                        │
│   return WwiseResult(ok=True, data=info)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ WAAPI Protocol (WebSocket)
┌─────────────────────────────────────────────────────────────┐
│ 6. WWISE AUTHORING - Esegue operazione                      │
│                                                              │
│   ✓ Object created: {type: Sound, id: 123, path: "..."}   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ Result bubbles back up
┌─────────────────────────────────────────────────────────────┐
│ 7. FRONTEND - Riceve risultato                              │
│                                                              │
│   {                                                          │
│     ok: true,                                                │
│     executionId: "exec_abc123_...",                         │
│     results: [                                               │
│       {node: "n1", ok: true, idemKey: "..."},              │
│       {node: "n2", ok: true, idemKey: "..."},              │
│       {node: "n3", ok: true, idemKey: "..."},              │
│       {node: "n4", ok: true, idemKey: "..."}               │
│     ]                                                        │
│   }                                                          │
│                                                              │
│   UI: Colora tutti i nodi in verde ✅                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎨 Design Patterns Utilizzati

### 1. Command Pattern
```python
# Command Bus = Invoker
# Ogni comando = Command
# Adapter = Receiver

bus.create_sound(payload)  # Invoca comando
  ↓
agent.create_sound(...)    # Esegue su receiver
```

### 2. Adapter Pattern
```python
# PyWwiseAdapter adatta WAAPI al dominio applicativo
WAAPI (complesso, posizionale) → Adapter → DTO semplici
```

### 3. Strategy Pattern
```python
# Registry: ogni NodeSpec definisce strategy di esecuzione
spec.run(data, bus)  # Strategy iniettata
```

### 4. Facade Pattern
```python
# Bus è facade su WAAPI, nasconde complessità
bus.audio_import(simple_payload)
  vs
agent.ak.wwise.core.audio.import_(complex_args)
```

### 5. Chain of Responsibility
```python
# Workflow runner: passa contesto step-by-step
Step1 → Context → Step2 → Context → Step3
```

---

## 🔐 Gestione Errori Stratificata

### Level 1: Adapter (WAAPI Errors)
```python
try:
    info = self.ak.wwise.core.object.create(...)
except WaapiException as e:
    return WwiseResult(ok=False, error=str(e), code="CREATE_FAILED")
```

### Level 2: Bus (Validation Errors)
```python
if not payload.get("filePath"):
    return {"ok": False, "error": "...", "code": "INVALID_INPUT"}
```

### Level 3: Runner (Execution Errors)
```python
if not result.get("ok"):
    return {
        "ok": False,
        "stopped": True,
        "stopAt": node_id,
        "results": results
    }
```

### Level 4: API (HTTP Errors)
```python
if not res.get("ok"):
    raise HTTPException(400, res.get("error"))
```

**Garanzia**: Nessun `500 Internal Server Error` non gestito!

---

## 📊 Stato e Contesto

### Contesto Runner (Transient)
```python
context = {
  "n1": {"objectId": "123", "name": "Sound1"},
  "n2": {},
  "n3": {}
}
```
- **Lifetime**: Singola esecuzione workflow
- **Uso**: Passare dati tra nodi
- **Storage**: In-memory

### Memo Idempotenza (Persistent)
```python
memo = {
  "hash_abc": {"ok": true, "data": {...}},
  "hash_def": {"ok": true, "data": {...}}
}
```
- **Lifetime**: Finché processo vivo
- **Uso**: Evitare riesecuzioni inutili
- **Storage**: In-memory (TODO: Redis per multi-process)

### Audit Log (Persistent)
```json
{
  "timestamp": "2024-10-29T12:00:00Z",
  "executionId": "exec_abc123",
  "command": "create_sound",
  "payload": {...},
  "result": {...}
}
```
- **Lifetime**: Permanente
- **Uso**: Compliance, debug, replay
- **Storage**: File `.jsonl` o database

---

## 🚀 Performance Considerations

### Ottimizzazioni Implementate

1. **Lock Granulare**
   ```python
   # Solo operazioni WAAPI locked, non validazioni
   validated = _validate(data)  # Unlocked
   with _WAAPI_LOCK:
     result = ak.wwise...       # Locked
   ```

2. **Idempotenza**
   ```python
   # Skip nodi già eseguiti
   if idem_key in memo and not force_rerun:
     return cached_result
   ```

3. **Lazy Compilation**
   ```python
   # Compila una volta, esegui N volte
   plan = compile_workflow(flow)  # Compile
   execute_plan(plan)             # Execute
   execute_plan(plan)             # Re-use plan
   ```

4. **Connection Pooling**
   ```python
   # Riusa connessione WAAPI
   with PyWwiseAgent() as agent:
     agent.create_sound(...)
     agent.audio_import(...)  # Stessa connessione
   ```

### Bottleneck Potenziali

1. **WAAPI Latency** (~50-200ms per call)
   - Soluzione: Batch operations future
   
2. **Serializzazione Lock** (operazioni sequenziali)
   - Soluzione: Read-only ops senza lock
   
3. **JSON Parsing** (workflow grandi)
   - Impatto: Minimo (<10ms per 100 nodi)

---

## 🧩 Estensibilità

### Aggiungere Nuova Interfaccia

```python
# Esempio: Server gRPC
class WwiseFlowGRPC(pb2_grpc.WwiseFlowServicer):
    def ExecuteWorkflow(self, request, context):
        flow = json.loads(request.workflow_json)
        result = execute_workflow_v2(flow)
        return pb2.WorkflowResult(**result)

# Stesso bus, nuova interfaccia!
```

### Aggiungere Nuovo Backend

```python
# Esempio: REAPER bridge
class ReaperAdapter:
    def render_regions(self, ...): -> Result
    def export_markers(self, ...): -> Result

# Registry nuovo nodo
self.register(NodeSpec(
    type="reaperRender",
    run=lambda data, _: reaper_adapter.render_regions(data)
))
```

### Aggiungere Storage Layer

```python
# Esempio: Redis per idempotenza distribuita
class RedisIdempotencyCache:
    def get(self, key): ...
    def set(self, key, value): ...

# Inject nel runner
runner = WorkflowRunner(cache=RedisIdempotencyCache())
```

---

## 📈 Metriche e Osservabilità

### Logging Strutturato

```python
logger.info("workflow.execution.start", extra={
    "executionId": exec_id,
    "nodeCount": len(plan),
    "userId": user_id
})

logger.info("node.execution.complete", extra={
    "nodeId": node_id,
    "type": node_type,
    "duration_ms": duration,
    "ok": result["ok"]
})
```

### Metrics (Future)

```python
# Prometheus-style
workflow_executions_total{status="success"} 142
workflow_executions_total{status="failed"} 8
node_execution_duration_seconds{type="createSound"} 0.12
waapi_calls_total{operation="create"} 450
```

---

## 🎯 Conclusioni

### Punti di Forza

✅ **Modularità** - Ogni layer indipendente  
✅ **Estensibilità** - Aggiungi nodi/interfacce senza refactoring  
✅ **Robustezza** - Errori gestiti, validazione upfront  
✅ **Testabilità** - Ogni layer testabile in isolamento  
✅ **Performance** - Lock granulari, idempotenza, caching  

### Limitazioni Attuali

⚠️ **Single-process** - Idempotenza non distribuita  
⚠️ **No Rollback** - Transazioni solo applicative  
⚠️ **No Parallel** - Esecuzione sequenziale (safe)  
⚠️ **Basic Audit** - Log semplici, no query complesse  

### Prossimi Passi

1. **Redis Cache** - Idempotenza distribuita
2. **Parallel Execution** - DAG branches concorrenti
3. **Advanced Audit** - Database relazionale per compliance
4. **REAPER/Unreal** - Bridge adapter estesi
5. **CI/CD Integration** - Workflow in pipeline automatiche

---

**L'architettura è solida, estensibile e pronta per la produzione! 🚀**