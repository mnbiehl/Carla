# Project Structure

## Root Directory
- `Makefile` - Main build configuration
- `pyproject.toml` - Python project configuration (Poetry)
- `README.md` - Project documentation
- `INSTALL.md` - Installation instructions
- `.serena/` - Serena MCP configuration
- `opencode.json` - Opencode MCP configuration

## Source Code (`source/`)
### Backend (`source/backend/`)
- `engine/` - Core audio engine implementation
  - `CarlaEngine*.cpp` - Engine classes
  - Parallel processing support
- `plugin/` - Plugin handling code
  - `CarlaPlugin*.cpp` - Plugin base classes and implementations
  - Support for various plugin formats
- Audio processing and MIDI handling

### Frontend (`source/frontend/`)
- `carla_mcp/` - MCP server implementation
  - `main.py` - MCP server entry point
  - `tools/` - MCP tool implementations
    - `connection.py` - Connection management
    - `plugins.py` - Plugin control
    - `parameters.py` - Parameter control
    - `routing.py` - Audio routing
    - `system.py` - System control
  - `backend/` - Backend bridge for MCP
  - `discovery/` - Plugin discovery
  - `resources/` - MCP resources
  - `utils/` - Utility functions
- PyQt5 GUI components
- `carla_host.py` - Main host application
- `carla_backend.py` - Backend Python bindings

### Other Components
- `bridges-plugin/` - Plugin bridge implementations
- `bridges-ui/` - UI bridges for different toolkits
- `discovery/` - Plugin discovery tools
- `includes/` - Header files and interfaces
- `jackbridge/` - JACK audio system bridge
- `libjack/` - JACK library implementation
- `modules/` - Third-party modules and libraries
- `native-plugins/` - Built-in plugins
- `plugin/` - Carla as plugin (LV2/VST)
- `tests/` - Test files
- `theme/` - UI themes
- `utils/` - Utility functions and helpers

## Resources
- `data/` - Application data files
- `resources/` - UI resources (icons, images, stylesheets)
- `doc/` - Documentation

## Build Output
- `build/` - Compiled binaries and modules
- `cmake/` - CMake build files