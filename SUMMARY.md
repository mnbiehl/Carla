# Carla MCP Development Session Summary

## Major Accomplishments

### 1. Fixed Critical MCP Server Stability Issues
- **Decoupled MCP server from engine lifecycle** - MCP now starts at app launch instead of engine start
- **Eliminated Wayland compositor crashes** - Engine stop/start no longer crashes the GUI
- **Fixed shutdown sequence** - Removed `os._exit(0)` that caused force termination
- **Added proper resource cleanup** - Backend bridge cleanup prevents memory leaks

### 2. Resolved Plugin Loading Problems  
- **Fixed LV2 plugin loading** - Discovered LV2 plugins need empty filename and URI as label
- **Corrected URI extraction** - Properly parse label field format "Bundle.lv2/uri:scheme:here"
- **Fixed database schema mismatch** - Plugin cache no longer fails with 'type' field errors
- **Added comprehensive debugging** - MCP tools now return detailed error information

### 3. Improved MCP API Design
- **Simplified plugin loading** - `add_plugin_by_name("PluginName")` now just works
- **Better error messages** - All debug info returned in MCP responses, not just terminal logs
- **Fixed backend bridge** - Proper return types with success/error details

### 4. Engine Mode Detection Fixed
- **Corrected patchbay mode detection** - Now properly reads `host.processMode` attribute
- **Working mode switching** - Can detect rack vs patchbay modes correctly

## Current State

### Working Features ✅
- MCP server starts/stops independently of engine
- Plugin discovery and database (442 plugins found)
- LV2 plugin loading via `add_plugin_by_name()`
- Engine mode detection (rack/patchbay)
- Basic patchbay group enumeration
- Stable engine stop/start without crashes

### Partially Working ⚠️
- Patchbay mode connections (needs port discovery)
- Engine mode switching (requires engine restart)

### Identified Issues 🔧
- **Patchbay connections fail** - Port ID offset issues in CarlaEngineGraph.cpp
- **Missing port discovery** - Need actual port names/IDs, not guessed ones
- **Insufficient routing tools** - Current MCP endpoints lack detail for patchbay workflow

## Technical Insights

### LV2 Plugin Loading Discovery
```python
# WRONG (what we tried initially):
host.add_plugin(build_type, plugin_type, "urn:zamaudio:ZamDelay", name, label, ...)

# CORRECT (what actually works):
host.add_plugin(build_type, plugin_type, "", "", "urn:zamaudio:ZamDelay", ...)
#                                       ↑    ↑    ↑
#                               filename  name  label (URI)
```

### Carla Architecture Understanding
- **Rack Mode**: Plugins connect in series automatically
- **Patchbay Mode**: Each plugin becomes isolated, requires manual connections
- **Port Offsets**: Audio ports need specific offset values, not simple 0,1,2 IDs
- **Engine Coupling**: Mode changes require engine restart (can't change while running)

### MCP Server Lifecycle
```
Before: App Start → Engine Start → MCP Start → Engine Stop → MCP Stop → Crash
After:  App Start → MCP Start → [Engine Start/Stop cycles] → App Close → MCP Stop
```

## Code Changes Made

### Files Modified
- `carla_host.py` - Decoupled MCP from engine lifecycle
- `backend_bridge.py` - Fixed plugin loading, added error details, fixed mode detection
- `carla_discovery_parser.py` - Fixed schema mismatch in PluginInfo.from_dict()
- `main.py` - Improved shutdown sequence and resource cleanup
- `signal_handler.py` - Removed force exit
- `plugins.py` - Return detailed error info from MCP tools

### Key Commits
- **15af1d7**: Fix critical MCP server issues and decouple from engine lifecycle

## Next Session Priorities

### High Priority 🔥
1. **Fix patchbay port discovery** - Implement proper port enumeration with correct IDs
2. **Add engine control tools** - Start/stop/restart engine via MCP
3. **Complete patchbay connection workflow** - Working audio routing tools

### Medium Priority 📋
4. Implement connection listing for patchbay mode
5. Add MIDI routing support
6. Add preset management for plugins
7. Transport controls (play/stop/record)

### Architecture Considerations 🏗️
- Patchbay mode requires much more sophisticated routing tools
- Current MCP API design may need expansion for complex workflows
- Consider adding visual patchbay representation in responses
- Need better integration between MCP tools and Carla's internal port management

## Development Notes
- Engine mode changes require engine restart - design MCP tools accordingly
- LV2 plugins behave differently from VST/LADSPA in loading API
- Carla assertions provide valuable debugging info for port connection issues
- MCP server stability is now solid foundation for advanced features