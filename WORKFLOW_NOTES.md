# Carla MCP Workflow Development Notes

## Overview
This document tracks the development of our Carla MCP workflow for processing looper tracks through effects chains. It includes what works, what doesn't, issues encountered, and ideas for future improvements.

## Current Date: 2025-07-12

## Working Configuration

### Basic Setup
- **Mode**: Always use patchbay mode
- **Input Routing**: Stereo looper outputs → mono Carla inputs
- **Output Routing**: All effects chains → Carla outputs 1/2 (stereo)
- **Connection Method**: JACK CLI commands for external connections

### What Works
- [Date] - Brief description of successful implementations

### What Doesn't Work
- [Date] - Issue description and any error messages

## Workflow Patterns

### Pattern 1: Single Looper Track with Effects
```
Looper Track → Carla Input (mono) → Effects Chain → Outputs 1/2
```
Status: [Not tested yet]
Notes: 

## Issues Encountered

### Issue Template
**Date**: 
**Problem**: 
**Error/Symptoms**: 
**Solution/Workaround**: 
**Status**: [Resolved/Pending/Won't Fix]

## Audio Effects Knowledge Base

### Research Summary (2025-07-12)
Found comprehensive guides for audio effects parameters and mixing practices.

### Key Parameter Guidelines

#### EQ (Equalization)
- **Purpose**: Balance frequencies, mostly subtractive
- **Vocals**: HPF ~100Hz, small cut ~1kHz, slight boost ~6kHz for brightness
- **General**: Cut narrow, boost wide; keep cuts under 3dB for clean sound
- **Reverb EQ**: HPF below 600Hz to reduce muddiness

#### Compression
- **Purpose**: Consistent levels by reducing peaks
- **Ratio**: 4:1 means 4dB over threshold becomes 1dB
- **Vocals (aggressive)**: 7:1 ratio, 500ms release, fast attack
- **Standard reference level**: -18dB (leaves headroom, models analog gear)

#### Reverb
- **Pre-delay**: 8-20ms (shorter for 1s decay, longer for 2s decay)
- **Decay time**: Shorter for upfront vocals, longer for spacey
- **Abbey Road Trick**: EQ reverb 600Hz-6kHz only
- **Wet/Dry**: 100% wet when on send/return, adjust to taste on insert

#### Delay
- **Slapback**: 0.1-0.15 of quarter note, -14 to -18dB behind main
- **Character**: Roll off high frequencies for analog/tape sound
- **Processing**: HPF/LPF on repeats to clean up

### TAP Reverberator Specific
- **Architecture**: Comb/allpass filter model
- **43 reverb types**: Different room simulations
- **HD versions**: More filters = smoother but more CPU
- **Enhanced Stereo**: Spatial spread (great for mono sources)
- **Components**: Can disable parts for different effects

### Best Practices
1. **Gain staging**: Average -18dB, peaks max -10dB
2. **Bussing**: Send copy to effect track, blend wet/dry
3. **Multiple reverbs**: Short bright + long dark = width + depth
4. **Ducking**: Compress reverb when signal present

## Ideas for Future Improvement

### Parameter Learning Strategy
- [ ] Build parameter range database for common plugins
- [ ] Create effect templates based on source material
- [ ] Develop adaptive parameter suggestions
- [ ] Test parameter changes and document results

### Automation
- [ ] Script to automatically connect new looper tracks
- [ ] Preset management for common effects chains
- [ ] Template setups for different genres/styles
- [ ] Parameter interpolation for smooth transitions

### Features
- [ ] Multi-track mixing capabilities
- [ ] Sidechain routing between tracks
- [ ] MIDI control mapping for live performance
- [ ] Session save/recall functionality
- [ ] Real-time parameter analysis

### Performance
- [ ] Optimize plugin loading times
- [ ] CPU usage monitoring
- [ ] Latency compensation
- [ ] Buffer size optimization guide

### User Experience
- [ ] Visual feedback for connection status
- [ ] Simplified command syntax
- [ ] Error recovery mechanisms
- [ ] Context-aware effect suggestions

## Code Snippets & Examples

### Useful Commands
```python
# Add frequently used command patterns here
```

## Questions & Research

### Open Questions
- How to handle plugin parameter ranges that aren't 0-1?
- Best practices for CPU-efficient effect chains?
- Optimal buffer sizes for low latency?
- Can we implement peak metering for gain staging?

### Things to Test
- [ ] Maximum number of simultaneous looper tracks
- [ ] Plugin compatibility list
- [ ] Latency measurements with different buffer sizes
- [ ] CPU usage with various effect chains
- [ ] Peak metering implementation feasibility

### Discovered Limitations
- ~~**No peak metering in MCP** (2025-07-12): Backend supports `get_input_peak_value()` and `get_output_peak_value()` but not exposed in MCP tools yet. OSC path `/peaks` exists for real-time data.~~ **RESOLVED** (2025-07-13): Implemented peak metering via monitoring resources. See "Peak Metering Implementation" below.

## Acoustic Guitar Chain Settings (SM58 Beta)

### Signal Path
Loop0 (mono sum) → EQ → Compressor → Reverb → Output 1/2

### Plugin Chain
1. **C* EqFA4p - 4-band parametric shelving equalizer**
   - Compensates for SM58 Beta proximity effect
   - Adds presence and air for acoustic guitar
   
2. **x42-comp - Dynamic Compressor Stereo**
   - Gentle compression for consistent dynamics
   - Preserves natural guitar transients
   
3. **Dragonfly Room Reverb**
   - Subtle room ambience
   - Natural space without muddiness

### Gain Staging
- Target: -18 dB average level
- Current levels: -13 to -14 dB (good headroom)
- No clipping detected

### Session Management
Save your work with:
```
mcp__carla-mcp__save_project("~/carla-projects/acoustic-guitar-sm58.carxp")
```

Load it back with:
```
mcp__carla-mcp__load_project("~/carla-projects/acoustic-guitar-sm58.carxp")
```

## Peak Metering Implementation

### Available Resources
- `monitoring://audio_levels` - Get peak levels for all plugins
- `monitoring://plugin_peak_values/{plugin_id}` - Get detailed peak data for specific plugin

### Usage Example
```python
# Check all plugin levels
ReadMcpResourceTool(server="carla-mcp", uri="monitoring://audio_levels")

# Check specific plugin with clipping detection
ReadMcpResourceTool(server="carla-mcp", uri="monitoring://plugin_peak_values/0")
```

### Features
- Linear and dB values
- Input/output monitoring per channel
- Clipping detection (> 0 dB)
- Headroom calculation
- -18 dB reference level

## Performance Observations

### CPU Usage
- Plugin X uses approximately Y% CPU
- Effect chains should be limited to Z plugins for stability

### Latency
- Current buffer size: 
- Measured latency: 
- Acceptable for live use: Yes/No

## Effect Parameter Learning Strategy

### Approach
1. **Start with known good values** from research (documented above)
2. **Test incrementally** - change one parameter at a time
3. **Document what sounds good** for different source materials
4. **Build templates** for common scenarios

### Parameter Discovery Process
1. Use `get_plugin_info()` to see all available parameters
2. Start with researched baseline values
3. Adjust in small increments (0.1 for 0-1 range)
4. Note CPU impact of different settings
5. Save successful combinations

### Effect Chain Strategy
1. **Basic chain**: EQ → Compression → Time-based effects (reverb/delay)
2. **Bus processing**: Send to reverb/delay on separate bus at 100% wet
3. **Frequency cleanup**: Always HPF reverbs to avoid mud
4. **Gain staging**: Keep -18dB average throughout chain

## Peak Metering Implementation

### Overview (2025-07-13)
Successfully implemented real-time peak metering by exposing the Carla backend's `get_input_peak_value()` and `get_output_peak_value()` methods through the MCP interface.

### Implementation Details
1. **Backend Bridge Enhancement**: Added peak value methods to `CarlaBackendBridge` class
   - `get_input_peak_value(plugin_id, is_left)` - Get input peak for left/right channel
   - `get_output_peak_value(plugin_id, is_left)` - Get output peak for left/right channel

2. **Monitoring Resources**: Implemented two MCP resources
   - `monitoring://audio_levels` - Get peak levels for all plugins at once
   - `monitoring://plugin_peak_values/{plugin_id}` - Get detailed peak info for specific plugin

3. **Features**:
   - Peak values in both linear (0.0-1.0+) and dB scales
   - Clipping detection (values > 1.0)
   - Headroom calculation from 0dB
   - Gain staging reference (-18dB standard)

### Usage Examples
```python
# Get levels for all plugins
levels = mcp.get_resource("monitoring://audio_levels")
# Returns: {"plugins": [{"id": 0, "name": "TAP Reverb", "input": {"left": -12.5, "right": -13.2}, ...}]}

# Get detailed levels for plugin 0
details = mcp.get_resource("monitoring://plugin_peak_values/0")
# Returns: {"input": {"left": {"linear": 0.2238, "dB": -13.0}, "clipping": false}, ...}
```

### Benefits
- Real-time gain staging monitoring
- Clipping detection for distortion prevention
- Proper level matching between plugins
- Visual feedback for mixing decisions

## Session Log

### Session Template
**Date**: 2025-07-12
**Goal**: 
**Actions Taken**: 
**Results**: 
**Next Steps**: 

### Session 1: Research & Planning
**Date**: 2025-07-12
**Goal**: Establish knowledge base for effect parameters
**Actions Taken**: 
- Researched mixing guides and parameter ranges
- Found specific TAP Reverberator documentation
- Created parameter learning strategy
**Results**: 
- Documented key parameter ranges for EQ, compression, reverb, delay
- Found TAP Reverberator has 43 presets with HD versions
- Established -18dB as standard gain staging reference
**Next Steps**: 
- Test basic reverb setup with looper track
- Document actual parameter ranges from plugin info
- Create first working effects chain 