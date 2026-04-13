"""Runtime discovery via the JTAGulator H (help) command.

Connects to the device, walks each menu level, and parses available commands.
Results are compared against the YAML config to flag drift: commands that
exist on the device but not in config, or vice versa."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .serial_conn import SerialConnection
from .config import DeviceConfig

logger = logging.getLogger(__name__)

# Matches lines like "J) JTAG" or "I) Identify JTAG pinout (IDCODE Scan)"
MENU_ENTRY_RE = re.compile(r"^\s*([A-Za-z])\)\s+(.+)$", re.MULTILINE)


@dataclass
class DiscoveredCommand:
    key: str
    description: str


@dataclass
class DiscoveredInterface:
    key: str
    description: str
    commands: list[DiscoveredCommand] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    general_commands: list[DiscoveredCommand] = field(default_factory=list)
    interfaces: list[DiscoveredInterface] = field(default_factory=list)
    config_only: list[str] = field(default_factory=list)   # in config but not on device
    device_only: list[str] = field(default_factory=list)   # on device but not in config

    def summary(self) -> str:
        lines = []
        lines.append(f"General commands: {len(self.general_commands)}")
        for iface in self.interfaces:
            lines.append(f"Interface {iface.key} ({iface.description}): {len(iface.commands)} commands")
        if self.config_only:
            lines.append(f"In config but not on device: {', '.join(self.config_only)}")
        if self.device_only:
            lines.append(f"On device but not in config: {', '.join(self.device_only)}")
        if not self.config_only and not self.device_only:
            lines.append("Config and device are in sync.")
        return "\n".join(lines)


def _parse_menu(text: str) -> list[DiscoveredCommand]:
    """Extract command entries from menu text."""
    return [
        DiscoveredCommand(key=m.group(1).upper(), description=m.group(2).strip())
        for m in MENU_ENTRY_RE.finditer(text)
    ]


def _identify_interfaces(entries: list[DiscoveredCommand]) -> tuple[list[DiscoveredCommand], list[DiscoveredCommand]]:
    """Split main menu entries into known interface selectors and general commands.

    Interface selectors are single-key entries that lead to submenus (JTAG, UART, GPIO, SWD).
    This uses a hardcoded set since the main interface keys are stable.
    """
    interface_keys = {"J", "U", "G", "S"}
    interfaces = [e for e in entries if e.key in interface_keys]
    general = [e for e in entries if e.key not in interface_keys]
    return interfaces, general


def discover(conn: SerialConnection, config: DeviceConfig | None = None) -> DiscoveryResult:
    """Run discovery against a connected JTAGulator.

    Sends H at the main menu, then enters each interface submenu to enumerate
    its commands. Optionally compares results against a DeviceConfig.
    """
    was_connected = conn.is_connected
    if not was_connected:
        conn.connect()

    result = DiscoveryResult()

    try:
        # Go to main menu and get help
        conn.send("")
        conn.read_until_prompt(timeout=1.0)
        main_help = conn.send_and_read("H", timeout=3.0)
        all_entries = _parse_menu(main_help)
        iface_entries, general_entries = _identify_interfaces(all_entries)

        result.general_commands = general_entries

        # Enter each interface submenu and enumerate its commands
        for iface in iface_entries:
            conn.send_and_read(iface.key, timeout=2.0)
            sub_help = conn.send_and_read("H", timeout=3.0)
            sub_commands = _parse_menu(sub_help)
            result.interfaces.append(
                DiscoveredInterface(
                    key=iface.key,
                    description=iface.description,
                    commands=sub_commands,
                )
            )
            # Return to main menu by sending a blank line or waiting for prompt
            conn.send("")
            conn.read_until_prompt(timeout=1.0)

        # Compare against config if provided
        if config:
            _compare(result, config)

    finally:
        if not was_connected:
            conn.disconnect()

    return result


def _compare(result: DiscoveryResult, config: DeviceConfig) -> None:
    """Populate config_only and device_only lists by comparing discovery
    results against the YAML config."""

    # Build sets of "interface_key.command_key" identifiers
    device_keys: set[str] = set()
    for cmd in result.general_commands:
        device_keys.add(f"general.{cmd.key}")
    for iface in result.interfaces:
        for cmd in iface.commands:
            device_keys.add(f"{iface.key}.{cmd.key}")

    config_keys: set[str] = set()
    for cmd in config.general_commands.values():
        config_keys.add(f"general.{cmd.key}")
    for iface in config.interfaces.values():
        for cmd in iface.commands.values():
            config_keys.add(f"{iface.key}.{cmd.key}")

    result.config_only = sorted(config_keys - device_keys)
    result.device_only = sorted(device_keys - config_keys)
