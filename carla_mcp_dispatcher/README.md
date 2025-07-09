# Carla MCP Dispatcher

A centralized MCP server that manages multiple Carla instances for multi-channel audio processing.

## Overview

The Carla MCP Dispatcher solves the limitation of Carla having only 2 system input/output ports by managing multiple Carla instances, each with unique JACK client names. This allows integration with applications like `loopers` that require multiple independent audio channels.

## Architecture

```
┌─────────────────────┐
│   MCP Client (AI)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  MCP Dispatcher     │ (Port 3000)
│  - Routes commands  │
│  - Manages instances│
└──────────┬──────────┘
           │
    ┌──────┴──────┬──────────┬──────────┐
    ▼             ▼          ▼          ▼
┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
│Carla-1 │  │Carla-2 │  │Carla-3 │  │Carla-N │
│Port3010│  │Port3011│  │Port3012│  │Port... │
└────────┘  └────────┘  └────────┘  └────────┘
    │           │           │           │
    ▼           ▼           ▼           ▼
  JACK        JACK        JACK        JACK
```

## Features

- **Dynamic Instance Management**: Create/destroy Carla instances on demand
- **Unique JACK Names**: Each instance has a unique JACK client name (e.g., Carla-loop1)
- **Command Routing**: Routes MCP commands to the appropriate instance
- **Resource Management**: Limits maximum instances and manages ports
- **Status Monitoring**: Track status of all instances

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Running the Dispatcher

```bash
python -m carla_mcp_dispatcher
```

### Environment Variables

- `CARLA_DISPATCHER_PORT`: Dispatcher MCP port (default: 3000)
- `CARLA_MAX_INSTANCES`: Maximum number of instances (default: 16)
- `CARLA_BASE_MCP_PORT`: Base port for instance MCP servers (default: 3010)
- `CARLA_EXECUTABLE`: Path to Carla executable (auto-detected if not set)
- `CARLA_DEFAULT_CHANNELS`: Default channel count for instances (default: 2)

### MCP Tools

#### Instance Management

- `create_instance(instance_id, channels)`: Create a new Carla instance
- `destroy_instance(instance_id)`: Destroy a Carla instance
- `list_instances()`: List all active instances
- `get_instance_status(instance_id)`: Get detailed instance status
- `get_dispatcher_status()`: Get overall dispatcher status

#### Plugin Management (per instance)

- `add_plugin(instance_id, plugin_type, plugin_name)`: Add plugin
- `remove_plugin(instance_id, plugin_id)`: Remove plugin
- `list_plugins(instance_id)`: List plugins

#### Parameter Control (per instance)

- `set_parameter(instance_id, plugin_id, parameter_id, value)`: Set parameter

#### MIDI Control (per instance)

- `send_midi_note(instance_id, plugin_id, channel, note, velocity, duration_ms)`: Send MIDI

## Example Workflow

```python
# Create instances for 4 loop channels
create_instance("loop1", channels=2)
create_instance("loop2", channels=2)
create_instance("loop3", channels=2)
create_instance("loop4", channels=2)

# Add effects to each loop
add_plugin("loop1", "lv2", "Calf Reverb")
add_plugin("loop2", "lv2", "GxDelay")
add_plugin("loop3", "lv2", "ZamCompX2")
add_plugin("loop4", "lv2", "GxChorus")

# Control parameters
set_parameter("loop1", 0, 0, 0.3)  # Set reverb room size
set_parameter("loop2", 0, 1, 0.5)  # Set delay time
```

## Integration with Loopers

In your loopers application, connect to the appropriate Carla JACK clients:

- Loop 1 output → Carla-loop1:audio-in
- Carla-loop1:audio-out → System playback
- Repeat for each loop channel

## Development

The dispatcher is designed to be extensible. Key modules:

- `dispatcher_server.py`: Main MCP server and tool registration
- `instance_manager.py`: Manages Carla process lifecycle
- `mcp_client.py`: Client for communicating with instance MCP servers
- `config.py`: Configuration management