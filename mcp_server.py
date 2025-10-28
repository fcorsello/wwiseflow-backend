# mcp_server.py — versione corretta per MCP Python SDK
import asyncio
from typing import Any, Dict

from mcp.server import Server
from mcp.server.stdio import stdio_server   # <— questo è il trasporto stdio
from mcp.types import Tool, TextContent

from app.command_bus import CommandBus
from app.workflow_runner import execute_workflow

server = Server("pywwise-mcp")
bus = CommandBus()

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_sound",
            description="Crea un oggetto Sound in Wwise",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "parentPath": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="set_output_bus",
            description="Imposta la reference OutputBus su un oggetto",
            input_schema={
                "type": "object",
                "properties": {
                    "objectId": {"type": "string"},
                    "busPath": {"type": "string"},
                },
                "required": ["objectId", "busPath"],
            },
        ),
        Tool(
            name="audio_import",
            description="Importa un file audio in un Sound",
            input_schema={
                "type": "object",
                "properties": {
                    "objectId": {"type": "string"},
                    "filePath": {"type": "string"},
                    "language": {"type": "string"},
                },
                "required": ["objectId", "filePath"],
            },
        ),
        Tool(
            name="project_save",
            description="Salva il progetto Wwise",
            input_schema={"type": "object", "properties": {}},
        ),
        Tool(
            name="execute_workflow",
            description="Esegue un workflow JSON contro il backend",
            input_schema={
                "type": "object",
                "properties": {
                    "flow": {"type": "object"},
                    "dry_run": {"type": "boolean"},
                },
                "required": ["flow"],
            },
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any] | None) -> list[TextContent]:
    arguments = arguments or {}
    if name == "create_sound":
        res = bus.create_sound(arguments)
    elif name == "set_output_bus":
        res = bus.set_output_bus(arguments)
    elif name == "audio_import":
        res = bus.audio_import(arguments)
    elif name == "project_save":
        res = bus.project_save({})
    elif name == "execute_workflow":
        res = execute_workflow(arguments["flow"], dry_run=arguments.get("dry_run", False))
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return [TextContent(type="text", text=str(res))]

async def main():
    # avvia il server MCP su STDIO (compatibile con Cline/CLI)
    async with stdio_server() as (read, write):
        await server.run(read, write)

if __name__ == "__main__":
    asyncio.run(main())
