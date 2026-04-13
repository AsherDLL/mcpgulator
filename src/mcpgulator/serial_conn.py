"""Serial connection manager for JTAGulator communication.

Handles opening/closing the serial port, sending commands, and reading
responses with proper timing and line termination."""

from __future__ import annotations

import os
import logging
import time

import serial

logger = logging.getLogger(__name__)

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 2.0
PROMPT_CHAR = ">"


class SerialConnection:
    """Manages the serial link to a JTAGulator device."""

    def __init__(
        self,
        port: str | None = None,
        baud: int | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.port = port or os.environ.get("MCPGULATOR_PORT", DEFAULT_PORT)
        self.baud = baud or int(os.environ.get("MCPGULATOR_BAUD", str(DEFAULT_BAUD)))
        self.timeout = timeout
        self._serial: serial.Serial | None = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> None:
        if self.is_connected:
            return
        logger.info("Connecting to %s at %d baud", self.port, self.baud)
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )
        # Give the device a moment to initialize after connection
        time.sleep(0.5)
        self._flush_input()

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Disconnected from %s", self.port)
        self._serial = None

    def send(self, data: str) -> None:
        """Send a string to the device, terminated with CR."""
        if not self.is_connected:
            raise ConnectionError("Not connected to JTAGulator")
        raw = (data + "\r").encode("ascii")
        self._serial.write(raw)
        self._serial.flush()
        logger.debug("TX: %r", data)

    def read_until_prompt(self, timeout: float | None = None) -> str:
        """Read from the device until we see the prompt character or timeout.

        Returns everything received up to (but not including) the prompt.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to JTAGulator")

        old_timeout = self._serial.timeout
        if timeout is not None:
            self._serial.timeout = timeout

        buf = bytearray()
        try:
            while True:
                chunk = self._serial.read(1)
                if not chunk:
                    break  # timeout
                buf.extend(chunk)
                if chunk == b">":
                    break
        finally:
            self._serial.timeout = old_timeout

        text = buf.decode("ascii", errors="replace").strip()
        logger.debug("RX: %r", text[:200])
        return text

    def read_lines(self, timeout: float | None = None) -> str:
        """Read available data until timeout, without waiting for a prompt.

        Useful for commands that produce output without returning to a prompt
        (continuous reads, passthrough mode, etc.).
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to JTAGulator")

        old_timeout = self._serial.timeout
        self._serial.timeout = timeout or self.timeout

        try:
            buf = self._serial.read(4096)
        finally:
            self._serial.timeout = old_timeout

        return buf.decode("ascii", errors="replace")

    def send_and_read(self, data: str, timeout: float | None = None) -> str:
        """Send a command and return the response up to the next prompt."""
        self.send(data)
        return self.read_until_prompt(timeout=timeout)

    def _flush_input(self) -> None:
        """Discard any stale data in the input buffer."""
        if self._serial:
            self._serial.reset_input_buffer()
