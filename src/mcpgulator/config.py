"""Load and validate the YAML command definitions, producing tool metadata
that the MCP server registers dynamically."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "jtagulator_commands.yaml"


@dataclass
class ParamDef:
    """Single parameter the device will prompt for after a command is sent."""
    name: str
    prompt: str
    type: str = "str"
    min: float | int | None = None
    max: float | int | None = None

    def json_schema_type(self) -> str:
        return {"int": "integer", "float": "number", "str": "string"}.get(self.type, "string")

    def to_json_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "type": self.json_schema_type(),
            "description": self.prompt,
        }
        if self.min is not None:
            schema["minimum"] = self.min
        if self.max is not None:
            schema["maximum"] = self.max
        return schema


@dataclass
class CommandDef:
    """A single command within an interface (or general)."""
    name: str
    key: str
    description: str
    interface_key: str | None  # None for general commands
    params: list[ParamDef] = field(default_factory=list)

    @property
    def tool_name(self) -> str:
        if self.interface_key:
            return f"{self.interface_key}_{self.name}"
        return self.name

    def input_schema(self) -> dict[str, Any]:
        if not self.params:
            return {"type": "object", "properties": {}, "required": []}
        props = {p.name: p.to_json_schema() for p in self.params}
        required = [p.name for p in self.params]
        return {"type": "object", "properties": props, "required": required}


@dataclass
class InterfaceDef:
    """A target interface (JTAG, UART, GPIO, SWD) with its commands."""
    name: str
    key: str
    description: str
    commands: dict[str, CommandDef] = field(default_factory=dict)


@dataclass
class DeviceConfig:
    """Full parsed configuration for the JTAGulator."""
    general_commands: dict[str, CommandDef] = field(default_factory=dict)
    interfaces: dict[str, InterfaceDef] = field(default_factory=dict)

    def all_commands(self) -> dict[str, CommandDef]:
        """All commands keyed by their MCP tool name."""
        result = {}
        for cmd in self.general_commands.values():
            result[cmd.tool_name] = cmd
        for iface in self.interfaces.values():
            for cmd in iface.commands.values():
                result[cmd.tool_name] = cmd
        return result


def _parse_params(raw_params: list[dict]) -> list[ParamDef]:
    return [
        ParamDef(
            name=p["name"],
            prompt=p.get("prompt", p["name"]),
            type=p.get("type", "str"),
            min=p.get("min"),
            max=p.get("max"),
        )
        for p in raw_params
    ]


def _parse_commands(commands: dict, interface_key: str | None) -> dict[str, CommandDef]:
    result = {}
    for name, spec in commands.items():
        result[name] = CommandDef(
            name=name,
            key=spec["key"],
            description=spec.get("description", name),
            interface_key=interface_key,
            params=_parse_params(spec.get("params", [])),
        )
    return result


def load_config(path: str | Path | None = None) -> DeviceConfig:
    """Load and parse the YAML config file into a DeviceConfig."""
    if path is None:
        path = os.environ.get("MCPGULATOR_CONFIG", str(DEFAULT_CONFIG))
    path = Path(path)

    with open(path) as f:
        raw = yaml.safe_load(f)

    config = DeviceConfig()

    if "general" in raw:
        config.general_commands = _parse_commands(
            raw["general"].get("commands", {}), interface_key=None
        )

    for iface_name, iface_spec in raw.get("interfaces", {}).items():
        iface = InterfaceDef(
            name=iface_name,
            key=iface_spec["key"],
            description=iface_spec.get("description", iface_name),
            commands=_parse_commands(iface_spec.get("commands", {}), interface_key=iface_name),
        )
        config.interfaces[iface_name] = iface

    return config
