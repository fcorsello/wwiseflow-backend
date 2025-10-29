"""
Node Registry: definizione formale dei contratti input/output per ogni tipo di nodo.
Ogni nodo dichiara:
- required: campi obbligatori
- optional: campi opzionali con default
- outputs: cosa esporta nel contesto (es. objectId)
- run: funzione di esecuzione che usa il CommandBus
"""
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass


@dataclass
class NodeSpec:
    """Specifica formale di un tipo di nodo"""
    type: str
    label: str  # Nome leggibile per UI
    description: str
    required: List[str]  # Input obbligatori
    optional: Dict[str, Any]  # Input opzionali con default
    outputs: List[str]  # Output esportati nel contesto
    run: Callable  # Funzione di esecuzione
    category: str = "wwise"  # Per raggruppare in UI


class NodeRegistry:
    """Registro centralizzato dei tipi di nodo supportati"""
    
    def __init__(self):
        self._nodes: Dict[str, NodeSpec] = {}
        self._register_builtin_nodes()
    
    def register(self, spec: NodeSpec):
        """Registra un nuovo tipo di nodo"""
        self._nodes[spec.type] = spec
    
    def get(self, node_type: str) -> Optional[NodeSpec]:
        """Recupera la specifica di un tipo di nodo"""
        return self._nodes.get(node_type)
    
    def list_types(self) -> List[str]:
        """Lista tutti i tipi di nodo disponibili"""
        return list(self._nodes.keys())
    
    def get_by_category(self, category: str) -> List[NodeSpec]:
        """Filtra nodi per categoria"""
        return [n for n in self._nodes.values() if n.category == category]
    
    def validate_node_data(self, node_type: str, data: Dict) -> Dict[str, Any]:
        """
        Valida i dati di un nodo contro la sua specifica.
        Restituisce: {"valid": bool, "errors": List[str], "missing": List[str]}
        """
        spec = self.get(node_type)
        if not spec:
            return {
                "valid": False,
                "errors": [f"Tipo nodo sconosciuto: {node_type}"],
                "missing": []
            }
        
        errors = []
        missing = []
        
        # Verifica campi obbligatori
        for field in spec.required:
            if field not in data or data[field] is None or data[field] == "":
                missing.append(field)
                errors.append(f"Campo obbligatorio mancante: {field}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "missing": missing
        }
    
    def _register_builtin_nodes(self):
        """Registra i nodi built-in di Wwise"""
        from .command_bus import CommandBus
        
        bus = CommandBus()
        
        # ============================================
        # CREATE SOUND
        # ============================================
        def run_create_sound(data: Dict, bus: CommandBus) -> Dict:
            """Crea un oggetto Sound in Wwise"""
            return bus.create_sound(data)
        
        self.register(NodeSpec(
            type="createSound",
            label="Create Sound",
            description="Crea un nuovo oggetto Sound nella gerarchia Actor-Mixer",
            required=["name"],
            optional={
                "parentPath": "/Actor-Mixer Hierarchy/Default Work Unit"
            },
            outputs=["objectId", "name", "path"],
            run=run_create_sound,
            category="wwise.objects"
        ))
        
        # ============================================
        # AUDIO IMPORT
        # ============================================
        def run_audio_import(data: Dict, bus: CommandBus) -> Dict:
            """Importa file audio in un Sound"""
            return bus.audio_import(data)
        
        self.register(NodeSpec(
            type="audioImport",
            label="Audio Import",
            description="Importa un file audio (.wav) in un oggetto Sound esistente",
            required=["objectId", "filePath"],
            optional={"language": "SFX"},
            outputs=[],  # Non produce nuovi output, modifica solo l'oggetto target
            run=run_audio_import,
            category="wwise.audio"
        ))
        
        # ============================================
        # SET REFERENCE (OutputBus)
        # ============================================
        def run_set_reference(data: Dict, bus: CommandBus) -> Dict:
            """Imposta reference OutputBus"""
            # Normalizza per il bus
            payload = {
                "objectId": data.get("objectId"),
                "busPath": data.get("valuePath")
            }
            return bus.set_output_bus(payload)
        
        self.register(NodeSpec(
            type="setReference",
            label="Set Output Bus",
            description="Imposta la reference OutputBus di un oggetto",
            required=["objectId", "valuePath"],
            optional={"reference": "OutputBus"},  # Per ora solo OutputBus
            outputs=[],
            run=run_set_reference,
            category="wwise.properties"
        ))
        
        # ============================================
        # PROJECT SAVE
        # ============================================
        def run_project_save(data: Dict, bus: CommandBus) -> Dict:
            """Salva il progetto Wwise"""
            return bus.project_save({})
        
        self.register(NodeSpec(
            type="projectSave",
            label="Save Project",
            description="Salva il progetto Wwise corrente",
            required=[],
            optional={},
            outputs=["saved"],
            run=run_project_save,
            category="wwise.project"
        ))
        
        # ============================================
        # QUERY WAQL (TODO)
        # ============================================
        def run_query_waql(data: Dict, bus: CommandBus) -> Dict:
            """Esegue query WAQL"""
            # TODO: implementare nel bus
            return {"ok": False, "error": "WAQL non ancora implementato"}
        
        self.register(NodeSpec(
            type="queryWAQL",
            label="Query WAQL",
            description="Esegue una query WAQL per recuperare oggetti",
            required=["waql"],
            optional={"returns": ["id", "name", "type"]},
            outputs=["results"],
            run=run_query_waql,
            category="wwise.query"
        ))
        
        # ============================================
        # SET PROPERTY (TODO)
        # ============================================
        def run_set_property(data: Dict, bus: CommandBus) -> Dict:
            """Imposta proprietà generica"""
            # TODO: implementare nel bus
            return {"ok": False, "error": "setProperty non ancora implementato"}
        
        self.register(NodeSpec(
            type="setProperty",
            label="Set Property",
            description="Imposta una proprietà su un oggetto (volume, pitch, etc)",
            required=["objectId", "property", "value"],
            optional={},
            outputs=[],
            run=run_set_property,
            category="wwise.properties"
        ))


# Singleton globale
_registry = NodeRegistry()


def get_registry() -> NodeRegistry:
    """Accesso al registry globale"""
    return _registry