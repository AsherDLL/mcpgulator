# mcpgulator

An MCP (Model Context Protocol) server for [JTAGulator](https://github.com/grandideastudio/jtagulator) by Joe Grand. Allows AI assistants that support MCP to interact with a JTAGulator device over serial, running JTAG/UART/SWD/GPIO scans and commands through a structured tool interface.

## How it works

The server uses a hybrid config-driven and discovery-based approach:

- A YAML config file (`config/jtagulator_commands.yaml`) defines all known commands, their parameters, and how to navigate the JTAGulator menu system to execute them. This is the source of truth for **how** to interact with each command.
- On startup, if a device is connected, the server sends the `H` (help) command through each menu level to discover what the device actually supports. It compares the results against the YAML config and logs any drift (commands on the device that are missing from the config, or config entries that the device does not recognize).

Adding or updating commands requires only editing the YAML file. The server dynamically registers MCP tools from the config on each start.

## Requirements

- Python 3.10+
- A JTAGulator connected via USB serial

## Installation

```
git clone https://github.com/YOUR_USERNAME/mcpgulator.git
cd mcpgulator
pip install -e .
```

This installs the `mcpgulator` command and all dependencies (`mcp`, `pyserial`, `pyyaml`). No separate `requirements.txt` needed.

## Configuration

Set environment variables to control the serial connection:

| Variable | Default | Description |
|---|---|---|
| `MCPGULATOR_PORT` | `/dev/ttyUSB0` | Serial port path |
| `MCPGULATOR_BAUD` | `115200` | Baud rate |
| `MCPGULATOR_CONFIG` | `config/jtagulator_commands.yaml` | Path to command definitions |

On macOS, the port is typically `/dev/tty.usbserial-*`. On Linux, `/dev/ttyUSB0` or `/dev/ttyACM0`.

## Usage

### Standalone

```
mcpgulator
```

Or:

```
python -m mcpgulator
```

### With Claude Code

**Enabling** -- add the server using the CLI:

```
claude mcp add mcpgulator mcpgulator -e MCPGULATOR_PORT=/dev/tty.usbserial-A100ABCD
```

Or add it manually to your MCP server configuration. For user-wide availability, edit `~/.claude/settings.json`. For a single project, create `.mcp.json` in the project root:

```json
{
  "mcpServers": {
    "mcpgulator": {
      "command": "mcpgulator",
      "env": {
        "MCPGULATOR_PORT": "/dev/tty.usbserial-A100ABCD"
      }
    }
  }
}
```

**Checking status**:

```
claude mcp list
```

**Disabling** -- remove the server:

```
claude mcp remove mcpgulator
```

Or delete the entry from `settings.json` / `.mcp.json`. The server only runs when a client spawns it, so removing the config entry is all it takes.

### With other MCP clients

Any MCP-compatible client can use this server over stdio transport. Start the server as a subprocess and communicate over stdin/stdout using the MCP protocol.

## Available tools

Tools are registered dynamically from the YAML config. The default config provides:

**General commands**

- `set_voltage` -- Set target I/O voltage (1.2V to 3.3V)
- `get_version` -- Display JTAGulator version information
- `get_help` -- Display available commands

**JTAG**

- `jtag_idcode_scan` -- Identify JTAG pinout via IDCODE Scan
- `jtag_bypass_scan` -- Identify JTAG pinout via BYPASS Scan
- `jtag_identify_rtck` -- Identify RTCK (adaptive clocking)
- `jtag_get_device_ids` -- Get JTAG Device ID(s)
- `jtag_test_bypass` -- Test BYPASS (TDI to TDO)
- `jtag_ir_dr_discovery` -- Instruction/Data Register (IR/DR) discovery
- `jtag_pin_mapper` -- Pin mapper (EXTEST Scan)
- `jtag_openocd_interface` -- OpenOCD interface

**UART**

- `uart_identify_pinout` -- Identify UART pinout
- `uart_identify_txd` -- Identify UART pinout (TXD only, continuous)
- `uart_passthrough` -- UART passthrough

**GPIO**

- `gpio_read_once` -- Read all channels (input, one shot)
- `gpio_read_continuous` -- Read all channels (input, continuous)
- `gpio_write_channels` -- Write all channels (output)
- `gpio_logic_analyzer` -- Logic analyzer (OLS/SUMP)

**SWD**

- `swd_idcode_scan` -- Identify SWD pinout via IDCODE Scan
- `swd_get_device_id` -- Get SWD Device ID

**Built-in (not config-driven)**

- `raw_command` -- Send arbitrary text to the device
- `discover` -- Run H-command discovery and compare against config
- `connect` -- Connect to the serial port
- `disconnect` -- Disconnect from the serial port

## Updating the command set

When JTAGulator firmware is updated with new commands:

1. Connect the device and use the `discover` tool (or run it manually) to see what the device reports.
2. Edit `config/jtagulator_commands.yaml` to add new command entries with their parameters.
3. Restart the server.

The YAML config structure is documented by example in the file itself.

## Project structure

```
mcpgulator/
  config/
    jtagulator_commands.yaml   # Command definitions
  src/mcpgulator/
    __init__.py
    __main__.py
    config.py                  # YAML config loader
    serial_conn.py             # Serial port manager
    discovery.py               # H-command discovery and config validation
    navigator.py               # Menu navigation and command execution
    server.py                  # MCP server entry point
```

## License

[GPL-3.0](LICENSE)
