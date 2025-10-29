# Extending WwiseFlow - Guida Pratica

## 🎯 Come Aggiungere Nuovi Nodi

L'architettura modulare rende **estremamente facile** aggiungere nuove funzionalità PyWwise. Segui questo pattern in 4 step.

---

## 📝 Pattern Generale

```
1. Adapter     → Implementa primitiva WAAPI
2. Command Bus → Wrapper con validazione
3. Registry    → Definisci contratto nodo
4. (Opzionale) → Endpoint REST/MCP
```

---

## 🔨 Esempio 1: Query WAQL

### Step 1: Adapter (`app/pywwise_adapter.py`)

```python
def query_waql(
    self,
    waql: str,
    returns: Optional[List[str]] = None
) -> WwiseResult:
    """Esegue query WAQL"""
    if returns is None:
        returns = ["id", "name", "type"]
    
    try:
        with _WAAPI_LOCK:
            results = self.ak.wwise.core.object.get(waql, returns)
        
        return WwiseResult(ok=True, data={"results": results})
    except Exception as e:
        return WwiseResult(ok=False, error=str(e), code="QUERY_FAILED")
```

### Step 2: Command Bus (`app/command_bus.py`)

```python
def query_waql(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    waql = payload.get("waql")
    returns = payload.get("returns", ["id", "name", "type"])
    
    if not waql:
        return {
            "ok": False,
            "error": "Campo 'waql' obbligatorio",
            "code": "INVALID_INPUT"
        }
    
    try:
        with PyWwiseAgent() as agent:
            res = agent.query_waql(waql, returns)
            return _normalize(res)
    except Exception as e:
        return _exc(e)
```

### Step 3: Registry (`app/node_registry.py`)

```python
def run_query_waql(data: Dict, bus: CommandBus) -> Dict:
    return bus.query_waql(data)

self.register(NodeSpec(
    type="queryWAQL",
    label="Query WAQL",
    description="Esegue query WAQL per recuperare oggetti Wwise",
    required=["waql"],
    optional={"returns": ["id", "name", "type"]},
    outputs=["results"],  # Lista di oggetti
    run=run_query_waql,
    category="wwise.query"
))
```

### Step 4: Endpoint REST (opzionale, `main.py`)

```python
@app.post("/api/wwise/query-waql")
def query_waql_endpoint(p: Payload):
    res = bus.query_waql(p.payload)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error"))
    return res
```

### Uso nel Workflow

```json
{
  "nodes": [
    {
      "id": "q1",
      "type": "queryWAQL",
      "data": {
        "waql": "$ from type Sound where name:contains 'Explosion'",
        "returns": ["id", "name", "path"]
      }
    }
  ]
}
```

---

## 🎵 Esempio 2: Set Property (Volume, Pitch)

### Step 1: Adapter

```python
def set_property(
    self,
    object_id: str,
    property_name: str,
    value: Any
) -> WwiseResult:
    """Imposta proprietà generica"""
    try:
        with _WAAPI_LOCK:
            self.ak.wwise.core.object.set_property(
                object=object_id,
                property=property_name,
                value=value
            )
        
        return WwiseResult(
            ok=True,
            data={
                "object": object_id,
                "property": property_name,
                "value": value
            }
        )
    except Exception as e:
        return WwiseResult(
            ok=False,
            error=str(e),
            code="SET_PROPERTY_FAILED"
        )
```

### Step 2: Command Bus

```python
def set_property(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    obj_id = payload.get("objectId")
    prop = payload.get("property")
    value = payload.get("value")
    
    if not all([obj_id, prop, value is not None]):
        return {
            "ok": False,
            "error": "objectId, property e value sono obbligatori",
            "code": "INVALID_INPUT"
        }
    
    try:
        with PyWwiseAgent() as agent:
            res = agent.set_property(obj_id, prop, value)
            return _normalize(res)
    except Exception as e:
        return _exc(e)
```

### Step 3: Registry

```python
def run_set_property(data: Dict, bus: CommandBus) -> Dict:
    return bus.set_property(data)

self.register(NodeSpec(
    type="setProperty",
    label="Set Property",
    description="Imposta una proprietà su un oggetto (Volume, Pitch, etc)",
    required=["objectId", "property", "value"],
    optional={},
    outputs=[],  # Non produce nuovi output
    run=run_set_property,
    category="wwise.properties"
))
```

### Uso nel Workflow

```json
{
  "nodes": [
    {
      "id": "n1",
      "type": "createSound",
      "data": {"name": "LoudSound"}
    },
    {
      "id": "n2",
      "type": "setProperty",
      "data": {
        "property": "Volume",
        "value": -6.0
      }
    }
  ],
  "edges": [
    {"source": "n1", "target": "n2"}
  ]
}
```

Il compilatore auto-wire `objectId` da `n1` a `n2`!

---

## 🎮 Esempio 3: Generate SoundBank

### Step 1: Adapter

```python
def generate_soundbank(
    self,
    bank_names: List[str],
    platforms: Optional[List[str]] = None
) -> WwiseResult:
    """Genera SoundBank"""
    if platforms is None:
        platforms = ["Windows"]
    
    try:
        with _WAAPI_LOCK:
            # Chiamata WAAPI reale
            self.ak.wwise.core.soundbank.generate(
                banks=bank_names,
                platforms=platforms
            )
        
        return WwiseResult(
            ok=True,
            data={"banks": bank_names, "platforms": platforms}
        )
    except Exception as e:
        return WwiseResult(
            ok=False,
            error=str(e),
            code="GENERATE_SOUNDBANK_FAILED"
        )
```

### Step 2: Command Bus

```python
def generate_soundbank(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    banks = payload.get("banks", [])
    platforms = payload.get("platforms", ["Windows"])
    
    if not banks:
        return {
            "ok": False,
            "error": "Lista 'banks' obbligatoria",
            "code": "INVALID_INPUT"
        }
    
    try:
        with PyWwiseAgent() as agent:
            res = agent.generate_soundbank(banks, platforms)
            return _normalize(res)
    except Exception as e:
        return _exc(e)
```

### Step 3: Registry

```python
def run_generate_soundbank(data: Dict, bus: CommandBus) -> Dict:
    return bus.generate_soundbank(data)

self.register(NodeSpec(
    type="generateSoundBank",
    label="Generate SoundBank",
    description="Genera SoundBank per piattaforme specificate",
    required=["banks"],
    optional={"platforms": ["Windows"]},
    outputs=["generated"],
    run=run_generate_soundbank,
    category="wwise.soundbanks"
))
```

### Uso nel Workflow

```json
{
  "nodes": [
    {
      "id": "sb1",
      "type": "generateSoundBank",
      "data": {
        "banks": ["Init", "Music", "SFX"],
        "platforms": ["Windows", "Mac", "PS5"]
      }
    }
  ]
}
```

---

## 🔄 Esempio 4: Nodo con Dipendenze Multiple

### Scenario: Duplicate Sound

Crea un Sound come clone di un esistente.

### Step 1: Adapter

```python
def duplicate_object(
    self,
    source_id: str,
    new_name: str,
    parent_path: Optional[str] = None
) -> WwiseResult:
    """Duplica un oggetto esistente"""
    try:
        parent = self.resolve_parent(parent_path)
        
        with _WAAPI_LOCK:
            # Prima copia l'oggetto
            duplicate = self.ak.wwise.core.object.copy(
                object=source_id,
                parent=parent,
                onNameConflict="rename"
            )
            
            # Poi rinomina
            self.ak.wwise.core.object.set_name(
                object=duplicate["id"],
                value=new_name
            )
        
        return WwiseResult(ok=True, data=duplicate)
    except Exception as e:
        return WwiseResult(
            ok=False,
            error=str(e),
            code="DUPLICATE_FAILED"
        )
```

### Step 3: Registry

```python
self.register(NodeSpec(
    type="duplicateSound",
    label="Duplicate Sound",
    description="Crea una copia di un Sound esistente",
    required=["sourceId", "name"],
    optional={"parentPath": None},
    outputs=["objectId"],
    run=lambda data, bus: bus.duplicate_object(data),
    category="wwise.objects"
))
```

### Uso nel Workflow

```json
{
  "nodes": [
    {
      "id": "n1",
      "type": "createSound",
      "data": {"name": "Original"}
    },
    {
      "id": "n2",
      "type": "duplicateSound",
      "data": {"name": "Copy1"}
    },
    {
      "id": "n3",
      "type": "duplicateSound",
      "data": {"name": "Copy2"}
    }
  ],
  "edges": [
    {"source": "n1", "target": "n2"},
    {"source": "n1", "target": "n3"}
  ]
}
```

Entrambi `n2` e `n3` ricevono automaticamente `sourceId` da `n1`!

---

## 🎨 Best Practices

### 1. Validazione Pre-flight

```python
def audio_import(self, object_id: str, wav_path: str) -> WwiseResult:
    # ✅ BUONO: Verifica esistenza file
    if not os.path.exists(wav_path):
        return WwiseResult(
            ok=False,
            error=f"File non trovato: {wav_path}",
            code="FILE_NOT_FOUND"
        )
    
    # ... resto della logica
```

### 2. Lock Solo su Operazioni WAAPI

```python
def set_property(self, obj_id: str, prop: str, value: Any):
    # ❌ CATTIVO: Lock troppo ampio
    with _WAAPI_LOCK:
        validated_value = _validate_property_value(prop, value)
        self.ak.wwise.core.object.set_property(...)
    
    # ✅ BUONO: Lock solo su chiamata WAAPI
    validated_value = _validate_property_value(prop, value)
    with _WAAPI_LOCK:
        self.ak.wwise.core.object.set_property(...)
```

### 3. Output Semantici

```python
# ✅ BUONO: Output chiari e utili
outputs=["objectId", "bankPath", "platforms"]

# ❌ CATTIVO: Output generici
outputs=["result"]
```

### 4. Categorie per UI

```python
# Organizza per dominio
category="wwise.objects"    # Create, Duplicate, Delete
category="wwise.audio"      # Import, Export
category="wwise.properties" # Set Property, Set Reference
category="wwise.soundbanks" # Generate, Convert
category="wwise.query"      # WAQL, Get Info
```

---

## 🧪 Testing dei Nuovi Nodi

### Test Unitario (Adapter)

```python
def test_set_property():
    agent = PyWwiseAgent()
    agent.connect()
    
    result = agent.set_property(
        object_id="test_obj",
        property_name="Volume",
        value=-6.0
    )
    
    assert result.ok
    assert result.data["value"] == -6.0
```

### Test Integrazione (Workflow)

```python
def test_property_workflow():
    workflow = {
        "nodes": [
            {"id": "n1", "type": "createSound", "data": {"name": "Test"}},
            {"id": "n2", "type": "setProperty", "data": {
                "property": "Volume",
                "value": -3.0
            }}
        ],
        "edges": [{"source": "n1", "target": "n2"}]
    }
    
    result = execute_workflow_v2(workflow)
    assert result["ok"]
```

---

## 📚 Checklist Estensione

Prima di committare un nuovo nodo, verifica:

- [ ] Implementato in `pywwise_adapter.py`
- [ ] Wrapper in `command_bus.py` con validazione
- [ ] Registrato in `node_registry.py` con contratto completo
- [ ] Input `required` ben definiti
- [ ] Output dichiarati correttamente
- [ ] Categoria assegnata
- [ ] Validazione pre-flight (file, parent, etc)
- [ ] Lock WAAPI su operazioni critiche
- [ ] Gestione errori con codici specifici
- [ ] Test unitario scritto
- [ ] Documentazione aggiunta

---

## 🎯 Roadmap Nodi Futuri

### Priority 1: Core Operations
- ✅ createSound
- ✅ audioImport
- ✅ setReference (OutputBus)
- 🔲 setProperty (generico)
- 🔲 queryWAQL
- 🔲 duplicateObject
- 🔲 deleteObject
- 🔲 moveObject

### Priority 2: SoundBanks
- 🔲 generateSoundBank
- 🔲 convertWAV (compress)
- 🔲 clearCache

### Priority 3: Batch Operations
- 🔲 batchImport (multipli file)
- 🔲 batchSetProperty
- 🔲 bulkRename

### Priority 4: Advanced
- 🔲 createEvent
- 🔲 createRandomContainer
- 🔲 createBlendContainer
- 🔲 setSwitchMapping
- 🔲 profilerCapture

---

## 🚀 Quick Reference

**Workflow completo per aggiungere un nodo:**

```bash
# 1. Adapter
vim app/pywwise_adapter.py
# Aggiungi def my_operation(self, ...): -> WwiseResult

# 2. Bus
vim app/command_bus.py
# Aggiungi def my_operation(self, payload): -> Dict

# 3. Registry
vim app/node_registry.py
# Aggiungi self.register(NodeSpec(...))

# 4. Test
curl -X POST http://localhost:8000/api/nodes/list
# Verifica che il nuovo nodo appaia nella lista

# 5. Workflow di test
vim test_my_node.json
curl -X POST http://localhost:8000/api/workflows/execute \
  -d @test_my_node.json

# 6. Commit
git add .
git commit -m "feat: add myOperation node"
```

---

**Hai dubbi su come implementare un nodo specifico? Chiedimi e ti preparo l'esempio completo!** 🎯