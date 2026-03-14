# Carla Plugin Loading Flow - Detailed Analysis

## Overview
This document traces the complete flow of how plugins are loaded in Carla, from initial API call to final integration in the audio engine.

## Entry Points

### Primary Entry Point: `CarlaEngine::addPlugin()`
Location: `/source/backend/engine/CarlaEngine.cpp` (line ~1077)

Two overloaded versions:
```cpp
// Version 1: With explicit binary type
bool addPlugin(BinaryType btype, PluginType ptype, 
               const char* filename, const char* name, const char* label, 
               int64_t uniqueId, const void* extra, uint options)

// Version 2: Using native binary type
bool addPlugin(PluginType ptype, const char* filename, 
               const char* name, const char* label, int64_t uniqueId, 
               const void* extra, uint options)
```

### Parameters:
- **btype**: Binary type (NATIVE, POSIX32, POSIX64, WIN32, WIN64, OTHER)
- **ptype**: Plugin type (LADSPA, DSSI, LV2, VST2, VST3, AU, etc.)
- **filename**: Path to plugin file
- **name**: Display name (optional)
- **label**: Plugin identifier within bundle
- **uniqueId**: Plugin-specific ID (VST uses this)
- **extra**: Type-specific extra data
- **options**: Loading options flags

## Loading Flow

### Step 1: Validation
```cpp
// Check engine is not closed
CARLA_SAFE_ASSERT_RETURN_ERR(!pData->isIdling, "An operation is still being processed");

// Validate plugin type
CARLA_SAFE_ASSERT_RETURN_ERR(ptype != PLUGIN_NONE, "Invalid plugin type");

// Additional checks for specific types
if (ptype == PLUGIN_DSSI)
    CARLA_SAFE_ASSERT_RETURN_ERR(label != nullptr && label[0] != '\0', 
                                 "DSSI label is missing");
```

### Step 2: ID Assignment
```cpp
uint id;
if (options & PLUGIN_OPTION_REPLACE_EXISTING) {
    // Reuse ID from existing plugin being replaced
    id = options - PLUGIN_OPTION_REPLACE_EXISTING;
} else {
    // Find next available ID
    id = pData->nextPluginId;
    if (id >= pData->maxPluginCount) {
        setLastError("Maximum number of plugins reached");
        return false;
    }
}
```

### Step 3: Bridge Decision
```cpp
bool preferBridges = pData->options.preferPluginBridges;
bool needsBridge = false;

// Check if bridging is needed
if (pData->options.processModeForced) {
    needsBridge = true;
} else if (btype == BINARY_NATIVE) {
    // Native plugins typically don't need bridging
} else {
    // Different architecture needs bridge
    needsBridge = true;
}
```

### Step 4: Plugin Creation
The engine calls the appropriate factory method based on plugin type:

```cpp
CarlaPluginPtr plugin;

switch (ptype) {
    case PLUGIN_LV2:
        plugin = CarlaPlugin::newLV2(initializer);
        break;
    case PLUGIN_VST2:
        plugin = CarlaPlugin::newVST2(initializer);
        break;
    case PLUGIN_VST3:
        plugin = CarlaPlugin::newVST3(initializer);
        break;
    // ... other types
}
```

Each factory method (`newLV2`, `newVST2`, etc.) is in its respective file:
- LV2: `/source/backend/plugin/CarlaPluginLV2.cpp`
- VST2: `/source/backend/plugin/CarlaPluginVST2.cpp`
- VST3: `/source/backend/plugin/CarlaPluginVST3.cpp`

### Step 5: Plugin Initialization

#### 5.1 Base Initialization
```cpp
// In CarlaPlugin constructor
CarlaPlugin::CarlaPlugin(CarlaEngine* engine, uint id)
    : pData(new ProtectedData(engine, id))
{
    pData->enabled = true;
    pData->client = new CarlaEngineClient(*this);
}
```

#### 5.2 Type-Specific Loading
Each plugin type implements `reload()`:
```cpp
// Example from LV2
bool CarlaPluginLV2::reload()
{
    // Load the actual plugin library
    lib_open(fBinary.getBuffer());
    
    // Get plugin descriptor
    const LV2_Descriptor* descriptor = lib_symbol("lv2_descriptor");
    
    // Instantiate plugin
    fHandle = descriptor->instantiate(descriptor, 
                                     pData->engine->getSampleRate(), 
                                     fBundlePath, 
                                     fFeatures);
    
    // Discover ports
    for (uint32_t i = 0; i < descriptor->port_count; ++i) {
        analyzePort(i);
    }
    
    // Activate plugin
    if (descriptor->activate)
        descriptor->activate(fHandle);
}
```

### Step 6: Engine Integration

#### 6.1 Add to Plugin Array
```cpp
pData->plugins[id].plugin = plugin;
pData->plugins[id].outsPeak[0] = 0.0f;
pData->plugins[id].outsPeak[1] = 0.0f;
```

#### 6.2 Update Audio Graph (Patchbay Mode)
```cpp
if (pData->options.processMode == ENGINE_PROCESS_MODE_PATCHBAY) {
    pData->graph.addPlugin(plugin);
}
```

#### 6.3 Send Callback
```cpp
callback(true, true, ENGINE_CALLBACK_PLUGIN_ADDED, id, 0, 0, 0, 0.0f, plugin->getName());
```

#### 6.4 Activate Plugin
```cpp
if (plugin->isEnabled() && !pData->aboutToClose) {
    plugin->setActive(true, true, true);
}
```

## Plugin Discovery Process

### Discovery Binary
Location: `/source/discovery/carla-discovery.cpp`

Runs as separate process for safety:
```cpp
// Main engine launches discovery
int pipe[2];
pipe2(pipe, O_CLOEXEC);

if (fork() == 0) {
    // Child process
    execl(discoveryPath, "carla-discovery", pluginPath, nullptr);
} else {
    // Parent reads discovery output
    CarlaPluginDiscoveryInfo info;
    readDiscoveryData(pipe[0], info);
}
```

### Discovery Output Format
```
// Example discovery output
carla-discovery::init::/path/to/plugin.so
carla-discovery::name::My Plugin
carla-discovery::label::myplugin
carla-discovery::maker::Plugin Company
carla-discovery::audio.ins::2
carla-discovery::audio.outs::2
carla-discovery::parameters.ins::5
carla-discovery::end::0
```

## Memory Management

### Smart Pointers
All plugins use `std::shared_ptr`:
```cpp
typedef std::shared_ptr<CarlaPlugin> CarlaPluginPtr;
```

### Plugin Array
Pre-allocated based on engine mode:
```cpp
// In rack mode
pData->maxPluginCount = MAX_RACK_PLUGINS;  // 16

// In patchbay mode  
pData->maxPluginCount = MAX_PATCHBAY_PLUGINS;  // 255

// Allocate array
pData->plugins = new EnginePluginData[pData->maxPluginCount];
```

## Error Handling

### Error Propagation
```cpp
// Set error message
setLastError("Failed to load plugin");

// Check from caller
if (!engine->addPlugin(...)) {
    const char* error = engine->getLastError();
    showError(error);
}
```

### Cleanup on Failure
```cpp
if (!plugin->init(filename, name, label, uniqueId)) {
    plugin.reset();  // Automatic cleanup via smart pointer
    return false;
}
```

## Thread Safety

### Engine State Checks
```cpp
// Prevent concurrent operations
CARLA_SAFE_ASSERT_RETURN_ERR(!pData->isIdling, 
                             "An operation is still being processed");
```

### Plugin Discovery
- Runs in separate process (completely isolated)
- No shared memory with main engine
- Communication via pipes only

### Graph Updates
```cpp
// Mutex protected in patchbay mode
const ScopedGraphLocker sgl(pData->graph);
pData->graph.addPlugin(plugin);
```

## Plugin Lifecycle

### Full Lifecycle:
1. **Discovery**: Find available plugins
2. **Loading**: Create plugin instance
3. **Initialization**: Load plugin code, discover ports
4. **Activation**: Enable processing
5. **Processing**: Handle audio/MIDI
6. **Deactivation**: Disable processing
7. **Cleanup**: Unload plugin

### State Transitions:
```
Unloaded → Loaded → Initialized → Active → Processing
    ↑                                          ↓
    ←←←←←←← Deactivated ←←←←←←←←←←←←←←←←←←←←←
```

## Performance Considerations

### Plugin Loading is NOT Real-time Safe:
- Memory allocation
- File I/O
- Library loading
- Discovery subprocess

### Optimizations:
- Plugin info cached after first discovery
- Bridged plugins load asynchronously
- UI can be opened separately (not blocking audio)

## Summary

The plugin loading flow in Carla is a complex but well-structured process that:
1. Validates all inputs
2. Manages plugin IDs and memory  
3. Handles different plugin formats uniformly
4. Provides safety through process isolation (discovery)
5. Integrates cleanly with the audio engine
6. Maintains thread safety throughout

This architecture allows Carla to support many plugin formats while maintaining stability and performance.