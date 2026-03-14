# Carla MCP Development TODO

## ✅ Session 1 Completed - Major Stability Fixes

### Session 1 Achievements (2025-07-07)
- [x] **Fixed MCP server crashes** - Decoupled from engine lifecycle to prevent Wayland crashes
- [x] **Resolved LV2 plugin loading** - Fixed URI handling for proper plugin instantiation
- [x] **Fixed database schema** - Plugin cache corruption resolved
- [x] **Improved error handling** - MCP tools now return detailed debug information
- [x] **Fixed engine mode detection** - Properly detects rack/patchbay modes
- [x] **Added resource cleanup** - Proper shutdown sequence prevents memory leaks

## ✅ Session 2 Completed - Patchbay & Multi-Channel Investigation

### Session 2 Achievements (2025-07-08)
- [x] **Implemented proper patchbay port connections** - Fixed port offset constants (255 for inputs, 510 for outputs)
- [x] **Added JACK application support** - New `add_jack_application` tool for external JACK clients
- [x] **Discovered multi-channel patchbay plugins** - Found Carla-Patchbay (16chan/32chan/64chan) internal plugins
- [x] **Enabled debug logging** - Built Carla with DEBUG=true and CARLA_CAPTURE_CONSOLE_OUTPUT for comprehensive logging
- [x] **Fixed patchbay group enumeration** - Updated to show actual plugin port counts
- [x] **Investigated multi-channel audio solutions** - Analyzed approaches for expanding beyond 2 system ports

## 🛣️ Journey Summary

### The Problem
Started with an ambitious goal: Create an MCP (Model Context Protocol) server to control Carla audio plugin host, enabling AI assistants to manipulate professional audio processing through natural language.

### Key Challenges Overcome

1. **MCP Server Integration** 
   - Initially tried OSC-based approach, switched to direct backend API integration
   - Fixed FastMCP server initialization order (tools must be registered BEFORE server starts)
   - Implemented proper session management and restart protocols

2. **Backend API Discovery**
   - Found that Carla has a rich Python backend API through `carla_host.py`
   - Created `CarlaBackendBridge` class to wrap the backend API for MCP tools

3. **Binary Type Detection Issues**
   - Root cause: `BINARY_NATIVE` was incorrectly set to 0 (`BINARY_NONE`)
   - Fixed: Proper platform detection to use `BINARY_POSIX64` (2) on Linux x86_64
   - Added fallback detection and error reporting

4. **Plugin Type Constants Bug** ⭐ **THE BIG FIX**
   - **Critical Discovery**: Plugin type constants were off by 1 for every type!
   - Wrong values: `PLUGIN_LV2 = 3`, `PLUGIN_LADSPA = 1`, etc.
   - Correct values: `PLUGIN_LV2 = 4`, `PLUGIN_LADSPA = 2`, etc.
   - This was the root cause of all "Invalid internal plugin" errors

5. **Plugin Discovery System**
   - Built comprehensive plugin discovery using `carla-discovery-native`
   - Created plugin database with search capabilities
   - Proper handling of LV2 bundles (directories) vs individual plugin files

6. **LV2 Plugin Format Complexities**
   - LV2 plugins are bundles (directories) containing multiple files
   - Backend expects bundle directory path as filename, not individual .so/.ttl files
   - Label should contain the LV2 URI for proper identification

## 🏗️ Current Architecture

```
Carla MCP Server
├── FastMCP Framework (SSE transport on localhost:3001)
├── CarlaBackendBridge (wraps carla_host backend API)
├── Plugin Discovery System
│   ├── CarlaDiscoveryParser (uses carla-discovery-native)
│   ├── PluginDatabase (SQLite-based caching)
│   └── PluginDiscoverer (orchestrates discovery)
└── MCP Tools
    ├── Connection Tools (test, engine control)
    ├── Plugin Tools (add, remove, list, search)
    ├── Parameter Tools (get/set plugin parameters)
    ├── MIDI Tools (send notes, control)
    └── Transport Tools (play, stop, record)
```

## ✅ What Works Now

### Core Plugin Management
- ✅ **Plugin Loading**: LV2, LADSPA, VST2, VST3 all work correctly
- ✅ **Plugin Discovery**: Full system scan with caching
- ✅ **Plugin Search**: Name, maker, category-based search
- ✅ **Plugin Listing**: Show loaded plugins with metadata
- ✅ **Plugin Removal**: Remove individual or all plugins

### Plugin Discovery & Database
- ✅ **Automatic Discovery**: Scans standard plugin directories
- ✅ **Plugin Caching**: SQLite database for fast repeated access
- ✅ **Multi-threaded Discovery**: Parallel plugin scanning
- ✅ **Type Detection**: Automatic plugin format detection

### MCP Integration
- ✅ **Server-Sent Events**: FastMCP with SSE transport
- ✅ **Tool Registration**: All tools properly exposed to Claude
- ✅ **Error Handling**: Comprehensive error reporting
- ✅ **Session Management**: Proper initialization and cleanup

### Backend Integration
- ✅ **Direct API Access**: No OSC overhead, direct Python calls
- ✅ **Engine Control**: Start/stop audio engine
- ✅ **Real-time Monitoring**: Plugin status and metadata

## 🔧 Current Issues

### Known Problems
1. **JACK Application Launch Failures**: External JACK apps (like loopers) fail due to missing symbols in Carla's bundled JACK library
2. **Multi-channel Patchbay Plugins**: Internal patchbay plugins don't expose ports to external JACK graph
3. **GUI Crashes During Discovery**: Plugin browser occasionally crashes during scan (backend continues working)
4. **Limited External I/O**: Carla hardcoded to 2 audio inputs/outputs for external JACK connectivity

### Session 2 Discoveries
1. **Port Offset Constants**: Audio ports require specific offsets (255 for inputs, 510 for outputs) - now fixed
2. **Internal Plugin Architecture**: Multi-channel patchbay plugins work internally but don't provide external JACK ports
3. **JACK Library Conflicts**: Carla's bundled JACK library missing functions needed by external applications
4. **Debug Logging**: Comprehensive logging now available via debug build and environment variables

### Architecture Issues
1. **Constants Duplication**: Plugin type constants defined in multiple places (violates DRY principle)
2. **No Error Recovery**: Plugin addition failures don't provide recovery suggestions
3. **Limited Plugin Metadata**: Some plugin properties not fully exposed

## 📋 HIGH PRIORITY TODO

### Multi-Channel Audio Solutions
- [ ] **Fix JACK Application Launch**: Resolve bundled JACK library conflicts preventing external JACK clients
- [ ] **Multiple Carla Instances**: Implement MCP tools to spawn and coordinate multiple Carla instances for multi-channel setups
- [ ] **Modify Carla for Configurable I/O**: C++ changes to make system audio port count configurable (long-term solution)
- [ ] **Alternative JACK Routing**: Investigate external tools (alsa_in/alsa_out) for additional I/O channels

### Core Functionality
- [ ] **Test Parameter Control**: Verify plugin parameter get/set functionality works
- [ ] **Test MIDI Functionality**: Ensure note on/off and control messages work
- [ ] **Fix GUI Crashes**: Investigate plugin discovery crashes and improve robustness
- [ ] **Add MCP Server Status to Carla UI**: Display MCP connection status, active connections, and server health in the GUI
- [ ] **JSON Effects Chain Tool**: Create JSON representation of complete effects chains (plugins, parameters, connections, files) and MCP tool to deploy entire chains atomically
  - Research Carla's `.carxp` project file format and leverage existing save/load infrastructure
  - Integrate with Carla's native project system for compatibility and robustness
- [ ] **Effects Chain Grouping System**: Add group ID/name system to differentiate and manage multiple input chains (guitar, bass, vocals, etc.) with proper chain identification and management
- [ ] **Parameter Adjustment & Gain Staging Research**: Research and implement improved parameter adjustment algorithms and automatic gain staging techniques
  - Study professional mixing practices for optimal parameter ranges
  - Implement intelligent parameter suggestions based on audio content analysis
  - Research adaptive gain staging that responds to input dynamics
  - Investigate frequency-aware parameter adjustment for different instruments
  - Add parameter learning system that improves suggestions over time

### Code Quality Improvements
- [x] **Eliminate Constants Duplication**: Created single source of truth in constants.py module
  - Imported all constants from carla_backend.py
  - Replaced hardcoded values in backend_bridge.py, carla_discovery_parser.py, and routing.py
  - Added proper fallback values for missing constants
  - Tested all imports and functionality
- [ ] **Add Comprehensive Error Handling**: Better error messages and recovery suggestions
- [ ] **Add Input Validation**: Validate plugin IDs, parameter ranges, etc.
- [ ] **Add Unit Tests**: Test suite for backend bridge and discovery system

## 📋 MEDIUM PRIORITY TODO

### Enhanced Plugin Management
- [ ] **Plugin Preset Management**: Save/load plugin presets
- [ ] **Plugin State Management**: Full plugin state save/restore
- [ ] **Plugin Chain Management**: Manage plugin signal routing
- [ ] **Plugin Categories**: Better organization and filtering

### Performance Optimizations
- [ ] **Lazy Loading**: Only discover plugins when needed
- [ ] **Background Discovery**: Non-blocking plugin scanning
- [ ] **Connection Pooling**: Optimize backend API calls
- [ ] **Memory Management**: Better cleanup of unused plugins

### User Experience
- [ ] **Natural Language Processing**: Better parsing of user requests
- [ ] **Smart Plugin Suggestions**: Recommend plugins based on context
- [ ] **Plugin Usage Analytics**: Track and suggest frequently used plugins
- [ ] **Documentation Generation**: Auto-generate help from tool definitions

## 📋 LOW PRIORITY / FUTURE

### Advanced Features
- [ ] **Multi-rack Support**: Manage multiple Carla instances
- [ ] **Session Templates**: Save/load complete session configurations
- [ ] **Real-time Visualization**: Audio levels, spectrum analysis
- [ ] **Plugin Sandboxing**: Isolate problematic plugins
- [ ] **Performance Monitoring**: CPU usage, latency tracking

### Integration Features
- [ ] **DAW Integration**: Connect to external DAWs
- [ ] **Hardware Control**: MIDI controller mapping
- [ ] **Network Audio**: Jack/ASIO network audio support
- [ ] **Cloud Presets**: Online preset sharing and discovery

### Developer Experience
- [ ] **Plugin Development Kit**: Tools for plugin developers
- [ ] **API Documentation**: Comprehensive API reference
- [ ] **Example Projects**: Sample applications using the MCP server
- [ ] **Performance Benchmarks**: Automated performance testing

## 🏆 Success Metrics

### Achieved ✅
- [x] **Basic Plugin Loading**: Can load major plugin formats
- [x] **Plugin Discovery**: Can find and catalog plugins
- [x] **MCP Integration**: Claude can control Carla through natural language
- [x] **Stable Backend**: No crashes during normal operation

### Target Goals 🎯
- [ ] **100% Plugin Type Support**: All formats including internal plugins
- [ ] **Sub-second Response Time**: Fast enough for real-time interaction
- [ ] **Zero-crash Reliability**: Robust error handling prevents crashes
- [ ] **Production Ready**: Suitable for professional audio work

## 🔬 Technical Debt

### Known Issues That Need Cleanup
1. **Hardcoded Paths**: Discovery tool path, plugin directories
2. **Magic Numbers**: Plugin type constants, buffer sizes
3. **Error Message Inconsistency**: Different error formats across tools
4. **Logging Inconsistency**: Different log levels and formats
5. **Resource Cleanup**: Some resources may not be properly cleaned up

### Architecture Improvements Needed
1. **Configuration System**: Centralized configuration management
2. **Plugin Loading Strategy**: More sophisticated plugin loading logic
3. **Error Recovery System**: Automatic recovery from common failures
4. **State Management**: Better tracking of system state
5. **Event System**: Plugin addition/removal events for UI updates

## 🚀 Next Sprint Focus

### Sprint Goal: Make `add_plugin_by_name` Work
1. Debug why database-driven plugin addition fails
2. Fix label format issues for different plugin types
3. Add comprehensive testing for all plugin addition methods
4. Improve error reporting for plugin addition failures

### Success Criteria
- [ ] `add_plugin_by_name` works for LV2 plugins
- [ ] `add_plugin_by_name` works for LADSPA plugins  
- [ ] `add_plugin_by_name` works for VST2/VST3 plugins
- [ ] Clear error messages when plugin addition fails
- [ ] Automated tests cover plugin addition scenarios

---

## 💡 Key Lessons Learned

1. **Constants Matter**: Off-by-one errors in constants can break entire systems
2. **Single Source of Truth**: Duplicated constants lead to maintenance nightmares
3. **Error Messages Are Critical**: Good error reporting saves hours of debugging
4. **Integration Testing**: End-to-end testing catches issues unit tests miss
5. **Documentation While Building**: Real-time documentation prevents knowledge loss

## 🙏 Acknowledgments

This project stands on the shoulders of giants:
- **Carla Audio Plugin Host**: Incredible foundation for audio plugin management
- **FastMCP Framework**: Elegant MCP server implementation
- **Claude AI**: The reason this MCP server exists!

**Big thanks to the debugging partnership between human intuition and AI systematic analysis - together we conquered the constants bug that had us stumped for hours!** 🎉