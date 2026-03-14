# Carla MCP Server - Patchbay Implementation Plan

## 🎯 **IMMEDIATE GOAL**
Implement patchbay control through the Carla MCP server to enable individual effects chains for each looper output.

## 📊 **CURRENT PROJECT STATUS**

### ✅ **What's Working (As of 2025-07-07)**
- **Plugin Loading System**: LV2, LADSPA, VST2, VST3 all work correctly
- **MCP Server**: Fully functional with FastMCP framework
- **Backend Integration**: Direct API access through `CarlaBackendBridge`
- **Discovery System**: Plugin search, discovery, and caching
- **Basic Tools**: Connection test, plugin add/remove, parameter control

### 📁 **Project Structure**
```
/home/michael/carla-mcp/carla-mcp-fork/  (git branch: carla-mcp)
├── source/frontend/carla_mcp/
│   ├── backend/backend_bridge.py     # Backend API wrapper
│   ├── tools/routing.py              # Audio routing MCP tools
│   ├── tools/plugins.py              # Plugin management tools
│   └── main.py                       # MCP server entry point
└── poetry.lock / pyproject.toml      # Dependencies
```

### 🚀 **How to Run**
- **MCP Server**: `poetry run carla-mcp` (SSE on localhost:3001)
- **Carla GUI**: `poetry run carla` (with MCP integration)
- **Test Connection**: Use `test_carla_connection()` MCP tool

## 🎵 **USER'S CURRENT SETUP**

### Loopers App JACK Ports
```bash
loopers:main_out_l/r          # Main mix output
loopers:loop0_out_l/r         # Individual loop outputs  
loopers:loop1_out_l/r
loopers:loop2_out_l/r
# ... etc for each loop track
```

### Carla Current State (Rack Mode)
```bash
Carla:audio-in1/2             # Single stereo input
Carla:audio-out1/2            # Single stereo output
```

### Current Limitation
- **Rack Mode**: All plugins process in series (Plugin1 → Plugin2 → Plugin3)
- **User Needs**: Individual effects chains (Loop0 → Delay, Loop1 → Reverb, etc.)
- **Solution**: Switch to **Patchbay Mode** for flexible routing

## 🔧 **TECHNICAL RESEARCH FINDINGS**

### Carla Engine Modes
```c
ENGINE_PROCESS_MODE_CONTINUOUS_RACK = 2    // Current: Series processing
ENGINE_PROCESS_MODE_PATCHBAY = 3           // Target: Parallel routing
```

### Available Backend API (from carla_backend.py)
```python
# Mode switching
def set_engine_option(option, value, valueStr)
    # Use: set_engine_option(ENGINE_OPTION_PROCESS_MODE, 3, "")

# Patchbay control  
def patchbay_connect(external, groupIdA, portIdA, groupIdB, portIdB)
def patchbay_disconnect(external, connectionId)
def patchbay_refresh(external)
```

### Constants Needed
```python
ENGINE_OPTION_PROCESS_MODE = 1
ENGINE_PROCESS_MODE_CONTINUOUS_RACK = 2
ENGINE_PROCESS_MODE_PATCHBAY = 3
```

## 📋 **IMPLEMENTATION PLAN**

### **Phase 1: Backend Bridge Extensions**
**File**: `/source/frontend/carla_mcp/backend/backend_bridge.py`

**Add Methods**:
```python
def set_engine_process_mode(self, mode: int) -> bool:
    """Switch between rack (2) and patchbay (3) modes"""
    
def get_engine_process_mode(self) -> int:
    """Get current engine mode (2=rack, 3=patchbay)"""
    
def patchbay_connect(self, group_a: int, port_a: int, group_b: int, port_b: int) -> bool:
    """Connect two ports in patchbay mode"""
    
def patchbay_disconnect(self, connection_id: int) -> bool:
    """Disconnect ports by connection ID"""
    
def patchbay_refresh(self) -> bool:
    """Refresh patchbay state"""
    
def get_patchbay_groups(self) -> List[Dict]:
    """Get all available port groups (plugins, system, etc.)"""
```

### **Phase 2: MCP Tools Extensions**  
**File**: `/source/frontend/carla_mcp/tools/routing.py`

**Add MCP Tools**:
```python
@mcp.tool()
def switch_to_patchbay_mode() -> str:
    """Switch Carla from rack mode to patchbay mode"""
    
@mcp.tool()  
def switch_to_rack_mode() -> str:
    """Switch Carla back to rack mode"""
    
@mcp.tool()
def get_current_engine_mode() -> str:
    """Get current engine mode (rack/patchbay)"""
    
@mcp.tool()
def get_patchbay_groups() -> str:
    """List all available port groups in patchbay"""
    
@mcp.tool()
def connect_patchbay_ports(group_a: str, port_a: str, group_b: str, port_b: str) -> str:
    """Connect two ports in patchbay mode"""
    
@mcp.tool()
def list_patchbay_connections() -> str:
    """Show all current patchbay connections"""
```

### **Phase 3: Integration Testing**
1. **Switch to patchbay mode** via MCP
2. **Add multiple plugins** (each gets separate ports)
3. **Connect specific loops** to specific plugins
4. **Verify JACK routing** with `jack_lsp` and `jack_connections`

## 🎯 **TARGET WORKFLOW**

### Step-by-Step User Experience
```bash
# 1. Switch Carla to patchbay mode
mcp: "Switch Carla to patchbay mode"

# 2. Add effects for different loops  
mcp: "Add a delay plugin for loop 0"
mcp: "Add a reverb plugin for loop 1"

# 3. Connect loops to effects
mcp: "Connect loop 0 output to the delay plugin input"
mcp: "Connect loop 1 output to the reverb plugin input"

# 4. Route effects to outputs
mcp: "Connect delay output to system output 1" 
mcp: "Connect reverb output to system output 2"
```

### Expected JACK Port Structure (Patchbay Mode)
```bash
# System
system:playback_1, system:playback_2

# Loopers (external)
loopers:loop0_out_l, loopers:loop0_out_r
loopers:loop1_out_l, loopers:loop1_out_r

# Carla Plugins (individual port groups)
Carla:Delay Plugin:input_1, Carla:Delay Plugin:output_1
Carla:Reverb Plugin:input_1, Carla:Reverb Plugin:output_1
```

## 🐛 **RECENT BUG FIXES COMPLETED**

### Fixed Issues
- ✅ **Plugin Type Constants**: Were off by 1 (LV2 was 3, now correctly 4)
- ✅ **Binary Type Detection**: Fixed BINARY_NONE → BINARY_POSIX64
- ✅ **Undefined Variables**: Removed `CARLA_BACKEND_AVAILABLE` references
- ✅ **Method Names**: Fixed `get_runtime_engine_info()` → `get_engine_info()`
- ✅ **Poetry Run**: Fixed `poetry run carla` with wrapper script

### Clean State
- No compilation errors
- All major plugin types (LV2, LADSPA, VST2, VST3) load successfully
- MCP server starts and responds to tools
- Backend bridge communication working

## 🔍 **KEY FILES TO MODIFY**

### 1. Backend Bridge (`backend_bridge.py`)
**Current Line Count**: ~350 lines
**Add**: Patchbay methods (~100 lines)
**Location**: Lines ~350+ (append new methods)

### 2. Routing Tools (`routing.py`) 
**Current Line Count**: ~190 lines
**Add**: Patchbay MCP tools (~150 lines)
**Location**: Lines ~190+ (append new tools)

## 🧪 **TESTING STRATEGY**

### Validation Steps
1. **Mode Switch Test**: Verify `get_current_engine_mode()` returns different values
2. **Port Discovery**: Check that patchbay mode exposes individual plugin ports
3. **Connection Test**: Manually connect ports and verify JACK routing
4. **Audio Test**: Route actual audio through individual effects chains
5. **Integration Test**: Full loopers → effects → outputs workflow

### Debug Commands
```bash
# Check JACK ports after mode switch
jack_lsp | grep -i carla

# Test MCP tools
mcp: "Get current engine mode"
mcp: "List patchbay groups"  
mcp: "Show current connections"
```

## 📚 **REFERENCE INFORMATION**

### Important Constants (from carla_backend.py)
- `ENGINE_OPTION_PROCESS_MODE = 1`
- `ENGINE_PROCESS_MODE_CONTINUOUS_RACK = 2`  
- `ENGINE_PROCESS_MODE_PATCHBAY = 3`
- `MAX_RACK_PLUGINS = 64`
- `MAX_PATCHBAY_PLUGINS = 255`

### Backend API Patterns
```python
# Mode switching
self.host.set_engine_option(ENGINE_OPTION_PROCESS_MODE, mode, "")

# Patchbay operations  
self.host.patchbay_connect(external=False, groupIdA, portIdA, groupIdB, portIdB)
self.host.patchbay_disconnect(external=False, connectionId)
```

## 🚨 **KNOWN CHALLENGES**

### Potential Issues
1. **Engine Restart**: Mode switching might require engine restart
2. **Port Discovery**: Finding correct group/port IDs for connections
3. **External Ports**: Handling loopers (external JACK client) connections
4. **State Persistence**: Maintaining connections across Carla restarts

### Mitigation Strategies
- Implement proper error handling for mode switch failures
- Add port discovery/mapping functions
- Test with simple internal connections first
- Document connection state for recovery

## 🎉 **SUCCESS CRITERIA**

### Minimum Viable Product
- ✅ Switch Carla between rack and patchbay modes via MCP
- ✅ Add plugins that appear as separate port groups
- ✅ Connect loopers outputs to specific plugin inputs
- ✅ Route plugin outputs to system outputs

### Full Implementation
- ✅ Natural language control of all routing operations
- ✅ Visual feedback in Carla patchbay GUI
- ✅ Robust error handling and validation
- ✅ Complete integration with existing MCP tools

---

## 🔄 **NEXT ACTIONS FOR NEW CLAUDE INSTANCE**

1. **Read this document** to understand current state
2. **Examine existing code** in `backend_bridge.py` and `routing.py`
3. **Start with Phase 1**: Add backend bridge patchbay methods
4. **Test incrementally**: Verify each method before proceeding
5. **Implement MCP tools**: Add user-facing patchbay controls
6. **Test full workflow**: Loopers → individual effects → outputs

**Priority**: HIGH - User is waiting to use individual effects chains for their loopers setup.

**Context**: This is a continuation of a successful plugin loading implementation. The foundation is solid, now we're adding advanced routing capabilities.