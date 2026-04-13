"""Menu navigator and command executor for JTAGulator.

Handles the state machine of navigating menus, sending parameters in response
to interactive prompts, and collecting command output."""

from __future__ import annotations

import logging

from .config import CommandDef
from .serial_conn import SerialConnection

logger = logging.getLogger(__name__)

# How long to wait for scan results (some scans take a while)
SCAN_TIMEOUT = 120.0
PROMPT_TIMEOUT = 5.0


class Navigator:
    """Drives the JTAGulator through its menu system to execute commands."""

    def __init__(self, conn: SerialConnection):
        self.conn = conn

    def ensure_main_menu(self) -> str:
        """Send a blank line and read until prompt to get back to the main menu."""
        return self.conn.send_and_read("", timeout=PROMPT_TIMEOUT)

    def execute(self, command: CommandDef, arguments: dict) -> str:
        """Execute a command definition with the given arguments.

        Navigates to the correct menu, sends the command key, fills in
        prompted parameters, and returns the collected output.
        """
        if not self.conn.is_connected:
            self.conn.connect()

        self.ensure_main_menu()

        # If this is an interface command, enter the interface submenu first
        if command.interface_key:
            iface_key = self._resolve_interface_key(command.interface_key)
            logger.debug("Entering interface: %s", iface_key)
            self.conn.send_and_read(iface_key, timeout=PROMPT_TIMEOUT)

        # Send the command key
        logger.debug("Sending command: %s (%s)", command.name, command.key)
        if command.params:
            self.conn.send(command.key)
            # For commands with params, we need to respond to each prompt
            output = self._fill_params(command, arguments)
        else:
            # No params, just send and collect output
            output = self.conn.send_and_read(command.key, timeout=SCAN_TIMEOUT)

        return self._clean_output(output)

    def _resolve_interface_key(self, interface_key: str) -> str:
        """Map interface name to its single-char menu key."""
        mapping = {
            "jtag": "J",
            "uart": "U",
            "gpio": "G",
            "swd": "S",
        }
        return mapping.get(interface_key.lower(), interface_key.upper())

    def _fill_params(self, command: CommandDef, arguments: dict) -> str:
        """Respond to each parameter prompt from the device."""
        collected = []

        for i, param in enumerate(command.params):
            value = arguments.get(param.name)
            if value is None:
                raise ValueError(f"Missing required parameter: {param.name}")

            # Read until the device sends its prompt
            prompt_text = self.conn.read_until_prompt(timeout=PROMPT_TIMEOUT)
            collected.append(prompt_text)
            logger.debug("Prompt received, sending %s=%s", param.name, value)
            self.conn.send(str(value))

        # After all params are sent, read the final output
        final = self.conn.read_until_prompt(timeout=SCAN_TIMEOUT)
        collected.append(final)

        return "\n".join(collected)

    def send_raw(self, text: str, timeout: float = SCAN_TIMEOUT) -> str:
        """Send arbitrary text and return the response. Escape hatch for
        commands not covered by the config."""
        if not self.conn.is_connected:
            self.conn.connect()
        return self.conn.send_and_read(text, timeout=timeout)

    @staticmethod
    def _clean_output(raw: str) -> str:
        """Strip prompt characters and excessive whitespace from output."""
        lines = raw.replace(">", "").splitlines()
        cleaned = [line.rstrip() for line in lines if line.strip()]
        return "\n".join(cleaned)
