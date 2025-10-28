
"""
Thin adapter around PyWwise to keep WAAPI usage in one place.
Uses positional signatures expected by PyWwise.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass
from pywwise import (
    new_waapi_connection,
    ProjectPath,
    EObjectType,
    ENameConflictStrategy,
    SystemPath,
    EBitDepth,
    ESampleRate,
)

@dataclass
class WwiseResult:
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class PyWwiseAgent:
    def __init__(self):
        self._conn = None

    def connect(self):
        if self._conn is None:
            # Garantisco un event loop nel thread corrente (necessario in threadpool)
            import asyncio
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            # ora posso creare la connessione WAAPI in sicurezza
            self._conn = new_waapi_connection()
        return self


    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._conn is not None:
            try:
                self._conn.disconnect()
            finally:
                self._conn = None

    # Convenience to access the underlying 'ak'
    @property
    def ak(self):
        if self._conn is None:
            raise RuntimeError("PyWwiseAgent not connected")
        return self._conn

    def ensure_default_parent(self) -> ProjectPath:
        # Actor-Mixer Default Work Unit (exists in the user's screenshot)
        return ProjectPath.actor_mixer_hierarchy(default_work_unit=True)

    def create_sound(self, name: str, parent_path: Optional[str] = None) -> WwiseResult:
        try:
            parent = ProjectPath(parent_path) if parent_path else self.ensure_default_parent()
            info = self.ak.wwise.core.object.create(
                name,
                EObjectType.SOUND,
                parent,
                ENameConflictStrategy.RENAME,
            )
            return WwiseResult(ok=True, data=info)
        except Exception as e:
            return WwiseResult(ok=False, error=str(e))

        # Not used here, but handy for quick file gen
    
    def generate_tone(self, out_wav: str):
        self.ak.wwise.debug.generate_tone_wav(SystemPath(out_wav), EBitDepth.INT_16, ESampleRate.SR_44100)

    def set_output_bus(self, object_id: str, bus_path: str) -> WwiseResult:
        try:
            self.ak.wwise.core.object.set_reference(
                object=object_id,
                reference="OutputBus",
                value=ProjectPath(bus_path),
            )
            return WwiseResult(ok=True, data={"object": object_id, "bus": bus_path})
        except Exception as e:
            return WwiseResult(ok=False, error=str(e))

    def audio_import(self, object_id: str, wav_path: str, language: str = "SFX") -> WwiseResult:
        try:
            self.ak.wwise.core.audio.import_(
                default={"importLanguage": language, "originalsSubFolder": ""},
                imports=[{"audioFile": wav_path, "objectPath": f"id:{object_id}"}],
                importOperation="useExisting",
            )
            return WwiseResult(ok=True, data={"object": object_id, "file": wav_path})
        except Exception as e:
            return WwiseResult(ok=False, error=str(e))

    def project_save(self) -> WwiseResult:
        try:
            self.ak.wwise.core.project.save()
            return WwiseResult(ok=True, data={"saved": True})
        except Exception as e:
            return WwiseResult(ok=False, error=str(e))
