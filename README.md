
# PyWwise + MCP Backend (Sample)

Backend di esempio che espone primitive Wwise via FastAPI e, in parallelo, come strumenti MCP.
L'obiettivo è avere **un solo motore** (command bus) usato sia dall'editor React Flow
(che invierà un JSON di workflow) sia dalla chat/agente tramite MCP.

## Struttura
- `app/pywwise_adapter.py`: wrapper minimale di PyWwise (create/import/setReference/save).
- `app/command_bus.py`: DTO in/ out e routing verso l'adapter.
- `app/workflow_runner.py`: esecutore semplice di grafi (nodi sequenziali).
- `main.py`: FastAPI con endpoint REST.
- `mcp_server.py`: server MCP che registra strumenti 1:1 con il bus.
- `requirements.txt`: dipendenze.
- `sample_workflow.json`: esempio di grafo.

## Setup rapido
```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

> Assicurati che **Wwise Authoring** sia avviato e che il progetto abbia
> una *Default Work Unit* sotto Actor-Mixer. WAAPI deve essere abilitato (porta 8080).

### Avvio FastAPI
```bash
uvicorn main:app --reload
# GET http://localhost:8000/health
# POST http://localhost:8000/api/workflows/execute
```

### Avvio MCP (stdio)
```bash
python mcp_server.py
```
Collega poi un client MCP (es. Cline) a questo server stdio.

## Esempio: eseguire il workflow di esempio
```bash
curl -X POST http://localhost:8000/api/workflows/execute -H "Content-Type: application/json" -d @sample_workflow.json
```

## Note
- Le chiamate PyWwise usano le *signature posizionali* (name, type, parent, conflict).
- Il bus salva il progetto con un nodo dedicato `projectSave`.
- Estendi `workflow_runner.py` per supportare nodi/edge avanzati e dry-run dettagliato.
