"""MCP server for JTAGulator.

Dynamically registers tools from the YAML config. On startup, if a device is
connected, it runs discovery (H command) to validate the config against the
actual device and logs any drift."""

from __future__ import annotations

import asyncio
import logging
import sys

from mcp.server import Server
from mcp.types import Tool, TextContent

from .config import load_config, DeviceConfig, CommandDef
from .serial_conn import SerialConnection
from .navigator import Navigator
from .discovery import discover

logger = logging.getLogger(__name__)

server = Server("mcpgulator")

_config: DeviceConfig | None = None
_conn: SerialConnection | None = None
_navigator: Navigator | None = None
_tools: dict[str, CommandDef] = {}


def _init() -> None:
    global _config, _conn, _navigator, _tools

    _config = load_config()
    _conn = SerialConnection()
    _navigator = Navigator(_conn)
    _tools = _config.all_commands()

    # Attempt discovery if a device is reachable
    try:
        _conn.connect()
        result = discover(_conn, _config)
        logger.info("Discovery result:\n%s", result.summary())
        if result.device_only:
            logger.warning(
                "Device has commands not in config: %s. "
                "Update jtagulator_commands.yaml to add support.",
                ", ".join(result.device_only),
            )
    except Exception as e:
        logger.info(
            "No device connected at startup (%s). "
            "Tools registered from config; connect a device before executing commands.",
            e,
        )


def _build_tool_list() -> list[Tool]:
    """Build MCP Tool definitions from the loaded config."""
    tools = []

    for tool_name, cmd in _tools.items():
        tools.append(
            Tool(
                name=tool_name,
                description=cmd.description,
                inputSchema=cmd.input_schema(),
            )
        )

    # Built-in tools not driven by config
    tools.append(
        Tool(
            name="raw_command",
            description="Send raw text to the JTAGulator and return the response. Use for commands not covered by the config.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Raw text to send"},
                    "timeout": {
                        "type": "number",
                        "description": "Response timeout in seconds (default 10)",
                    },
                },
                "required": ["text"],
            },
        )
    )
    tools.append(
        Tool(
            name="discover",
            description="Run discovery against the connected JTAGulator. Sends H through all menus and compares available commands against the YAML config.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        )
    )
    tools.append(
        Tool(
            name="connect",
            description="Connect to the JTAGulator serial port.",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {
                        "type": "string",
                        "description": "Serial port path (e.g. /dev/ttyUSB0). Uses MCPGULATOR_PORT env var if not specified.",
                    },
                    "baud": {
                        "type": "integer",
                        "description": "Baud rate (default 115200)",
                    },
                },
                "required": [],
            },
        )
    )
    tools.append(
        Tool(
            name="disconnect",
            description="Disconnect from the JTAGulator serial port.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        )
    )

    return tools


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _build_tool_list()


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await asyncio.to_thread(_handle_tool, name, arguments)
    except Exception as e:
        result = f"Error: {e}"
    return [TextContent(type="text", text=result)]


def _handle_tool(name: str, arguments: dict) -> str:
    """Dispatch a tool call. Runs in a thread to avoid blocking the event loop
    on serial I/O."""

    if name == "raw_command":
        timeout = arguments.get("timeout", 10.0)
        return _navigator.send_raw(arguments["text"], timeout=timeout)

    if name == "discover":
        if not _conn.is_connected:
            _conn.connect()
        result = discover(_conn, _config)
        return result.summary()

    if name == "connect":
        port = arguments.get("port")
        baud = arguments.get("baud")
        if port:
            _conn.port = port
        if baud:
            _conn.baud = baud
        _conn.connect()
        return f"Connected to {_conn.port} at {_conn.baud} baud"

    if name == "disconnect":
        _conn.disconnect()
        return "Disconnected"

    cmd = _tools.get(name)
    if not cmd:
        return f"Unknown tool: {name}"

    return _navigator.execute(cmd, arguments)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    _init()

    from mcp.server.stdio import stdio_server

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
