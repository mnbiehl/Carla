#!/usr/bin/env python3
"""Test script to compare performance with and without parallel processing."""

import sys
import time
sys.path.insert(0, '/home/michael/carla-mcp/carla-mcp-fork/source/frontend')

import carla_backend as backend
import carla_host

def test_performance(parallel_enabled):
    """Test performance with given parallel processing setting."""
    # Initialize the host
    host = carla_host.CarlaHostQtNull()
    
    # Set parallel processing option
    host.set_engine_option(backend.ENGINE_OPTION_PARALLEL_PROCESSING, 
                          1 if parallel_enabled else 0, "")
    
    # Initialize engine in rack mode
    if not host.engine_init("Jack", f"CarlaTest_{parallel_enabled}"):
        print(f"ERROR: Failed to initialize engine")
        return None
    
    # Add multiple plugins to stress the system
    plugins = []
    plugin_names = ["audiogain_s", "lfo", "midi_transpose", "audiogain_s", "lfo"]
    
    for i, name in enumerate(plugin_names):
        plugin_id = host.add_plugin(backend.BINARY_NATIVE, backend.PLUGIN_INTERNAL, 
                                   "", "", name, 0, None, 0)
        if plugin_id >= 0:
            plugins.append(plugin_id)
            print(f"  Added {name} (ID: {plugin_id})")
    
    # Wait for plugins to stabilize
    time.sleep(2)
    
    # Measure performance
    measurements = []
    for i in range(10):
        info = host.get_runtime_engine_info()
        if info and 'load' in info:
            measurements.append(info['load'])
        time.sleep(0.1)
    
    # Calculate average load
    avg_load = sum(measurements) / len(measurements) if measurements else 0
    
    # Close the engine
    host.engine_close()
    
    return avg_load

# Test without parallel processing
print("Testing WITHOUT parallel processing...")
load_sequential = test_performance(False)
print(f"Average CPU load (sequential): {load_sequential:.2f}%\n")

time.sleep(1)

# Test with parallel processing
print("Testing WITH parallel processing...")
load_parallel = test_performance(True)
print(f"Average CPU load (parallel): {load_parallel:.2f}%\n")

# Compare results
if load_sequential and load_parallel:
    if load_parallel < load_sequential:
        improvement = ((load_sequential - load_parallel) / load_sequential) * 100
        print(f"Parallel processing reduced CPU load by {improvement:.1f}%")
    else:
        print("No improvement observed (this may be due to light plugin load)")
else:
    print("Could not compare results")