# Carla Multithreading Design Proposal

## Current Architecture (Single-threaded Audio Processing)

### Plugin Loading Flow
```
UI/API Request
    |
    v
CarlaEngine::addPlugin()
    |
    +---> Validate parameters
    |
    +---> Assign plugin ID
    |
    +---> Determine if bridging needed
    |
    +---> Create plugin instance
    |         |
    |         +---> CarlaPlugin::newLV2()  [Type-specific factory]
    |         +---> CarlaPlugin::newVST2()
    |         +---> CarlaPlugin::newNative()
    |         +---> etc.
    |
    +---> plugin->reload()  [Initialize plugin]
    |
    +---> Add to engine plugin array
    |
    +---> Update audio graph (if patchbay mode)
    |
    v
Plugin Ready for Processing
```

### Current Audio Processing Flow (Rack Mode)
```
JACK/Audio Callback (Audio Thread - Real-time)
    |
    v
CarlaEngineJack::handleJackProcessCallback()
    |
    v
EngineInternalGraph::processRack()
    |
    v
RackGraph::process()
    |
    +---> For each plugin (SERIAL):
    |       |
    |       +---> Copy buffers
    |       +---> plugin->process()
    |       +---> Output becomes next input
    |
    v
Audio Output
```

### Current Thread Model
```
┌─────────────────────────────────────────────────────────────┐
│                      Main Process                           │
├─────────────────────┬───────────────────┬─────────────────┤
│   Main/UI Thread    │  Audio Thread     │ Discovery Thread│
│   - GUI updates     │  - JACK callback  │ - Plugin scan   │
│   - User input      │  - Plugin process │ - Metadata      │
│   - Parameter queue │  - RT constraints │ - Subprocess    │
└─────────────────────┴───────────────────┴─────────────────┘
```

## Proposed Multithreading Architecture

### Option 1: Direct Plugin Threading (Complex)
```
JACK/Audio Callback
    |
    v
MultiThreadedRackGraph::process()
    |
    +---> Distribute to worker threads
    |       |
    |       +---> Thread 1: Plugin 0 (e.g., EQ)
    |       +---> Thread 2: Plugin 1 (e.g., NAM Guitar)
    |       +---> Thread 3: Plugin 2 (e.g., NAM Bass)
    |
    +---> Synchronize (wait for completion)
    |
    +---> Merge outputs
    |
    v
Audio Output

Challenges:
- Complex synchronization
- Plugin thread safety issues
- Latency from thread sync
- Buffer management complexity
```

### Option 2: Carla-in-Carla Threading (Recommended)
```
Main Carla Instance (JACK Client)
    |
    +---> Carla-Rack Plugin 1 (Thread 1)
    |       |
    |       +---> Chain: Input 1 → EQ → Compressor
    |
    +---> Carla-Rack Plugin 2 (Thread 2)
    |       |
    |       +---> Chain: Input 2 → Gate → NAM → Cabinet
    |
    +---> Carla-Rack Plugin 3 (Thread 3)
    |       |
    |       +---> Chain: Input 3 → NAM → Cabinet
    |
    +---> Regular Plugin (Main Thread)
    |       |
    |       +---> Reverb (receives all outputs)
    |
    v
Audio Output

Advantages:
- Uses existing, tested code
- Each Carla-Rack is fully independent
- Natural plugin boundaries
- Simpler synchronization
```

### Detailed Carla-in-Carla Implementation

#### 1. Plugin Structure
```
Main Carla Engine
    |
    +---> plugins[0]: Carla-Rack "Guitar Chain"
    |       |
    |       +---> Internal Engine (Dummy driver)
    |       +---> Plugins: EQ → Compressor
    |       +---> Runs in Thread Pool Worker 1
    |
    +---> plugins[1]: Carla-Rack "Electric Chain"
    |       |
    |       +---> Internal Engine (Dummy driver)
    |       +---> Plugins: Gate → NAM → Cabinet
    |       +---> Runs in Thread Pool Worker 2
    |
    +---> plugins[2]: Carla-Rack "Bass Chain"
    |       |
    |       +---> Internal Engine (Dummy driver)
    |       +---> Plugins: NAM → Cabinet
    |       +---> Runs in Thread Pool Worker 3
    |
    +---> plugins[3]: Reverb (regular plugin)
            |
            +---> Processes in main audio thread
            +---> Receives merged outputs
```

#### 2. Threading Model
```
┌─────────────────────────────────────────────────────────────┐
│                    Main Carla Process                       │
├─────────────────┬──────────────────┬───────────────────────┤
│  JACK Thread    │  Worker Pool     │   Other Threads       │
│  (Main Audio)   │  (3 threads)     │                       │
│                 │                   │                       │
│  1. Receive     │  Thread 1:       │  - GUI Thread         │
│     audio       │   Process        │  - Discovery Thread   │
│  2. Dispatch    │   Guitar Chain   │  - Parameter Thread   │
│     to workers  │                   │                       │
│  3. Wait for    │  Thread 2:       │                       │
│     completion  │   Process        │                       │
│  4. Process     │   Electric Chain │                       │
│     reverb      │                   │                       │
│  5. Output      │  Thread 3:       │                       │
│                 │   Process        │                       │
│                 │   Bass Chain     │                       │
└─────────────────┴──────────────────┴───────────────────────┘
```

#### 3. Audio Flow with Threading
```
Time →

JACK Callback Start
    |
    +---> Copy inputs to worker buffers (parallel)
    |       |
    |       +---> Buffer 1 → Worker 1
    |       +---> Buffer 2 → Worker 2
    |       +---> Buffer 3 → Worker 3
    |
    +---> Signal workers to start
    |
    +---> Workers process in parallel:
    |       |
    |       +---> [Thread 1] Guitar: EQ → Compressor
    |       +---> [Thread 2] Electric: Gate → NAM → Cab
    |       +---> [Thread 3] Bass: NAM → Cab
    |
    +---> Wait for all workers (barrier sync)
    |
    +---> Merge worker outputs
    |
    +---> Process reverb (main thread)
    |
    +---> Copy to JACK output buffers
    |
    v
JACK Callback Complete
```

### Implementation Steps

#### Phase 1: Thread-Safe Carla-Rack Plugin
1. Create `CarlaPluginNativeThreaded` class
2. Add worker thread to native plugin
3. Implement lock-free audio buffer exchange
4. Test with single instance

#### Phase 2: Thread Pool Management
1. Create thread pool for worker plugins
2. Implement work distribution
3. Add synchronization barriers
4. Test with multiple instances

#### Phase 3: Integration
1. Modify plugin loading to use threaded variant
2. Add configuration for thread assignment
3. Implement CPU affinity (optional)
4. Performance testing and optimization

### Key Design Decisions

1. **Why Carla-in-Carla?**
   - Reuses all existing plugin hosting code
   - Natural boundary for threading (entire chain per thread)
   - Avoids plugin thread-safety issues
   - Simpler than making individual plugins thread-safe

2. **Thread Synchronization**
   - Use lock-free ring buffers for audio
   - Barrier synchronization for worker completion
   - No mutexes in audio path

3. **Buffer Management**
   - Pre-allocated buffers per worker
   - Zero-copy where possible
   - Cache-aligned for performance

4. **Latency Considerations**
   - Additional latency = synchronization overhead
   - Estimated: < 0.5ms with proper implementation
   - Compensated by overall CPU reduction

### Performance Expectations

#### Current (Serial Processing)
- 3 NAM plugins @ 60% DSP load on single core
- Risk of dropouts under load

#### With Threading
- Each NAM on separate core
- ~20% DSP load per core
- Main thread overhead ~10% for dispatch/merge
- Total: Better headroom, no dropouts

### Risks and Mitigation

1. **Thread Synchronization Overhead**
   - Mitigation: Lock-free design, minimal sync points

2. **Increased Latency**
   - Mitigation: Optimize barriers, consider lock-free alternatives

3. **Debugging Complexity**
   - Mitigation: Comprehensive logging, thread visualization tools

4. **Plugin Compatibility**
   - Mitigation: Carla-in-Carla isolates plugins completely