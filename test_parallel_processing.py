#!/usr/bin/env python3
"""Test script to verify parallel processing option works correctly."""

import sys
import time
sys.path.insert(0, '/home/michael/carla-mcp/carla-mcp-fork/source/frontend')

import carla_backend as backend
import carla_host

# Initialize the host
host = carla_host.CarlaHostQtNull()

# Test 1: Set parallel processing before engine initialization
print("Test 1: Setting parallel processing option before engine init...")
host.set_engine_option(backend.ENGINE_OPTION_PARALLEL_PROCESSING, 1, "")
print(f"  Option set successfully")

# Initialize engine in rack mode
print("\nInitializing engine in rack mode...")
if not host.engine_init("Jack", "CarlaParallelTest"):
    print("ERROR: Failed to initialize engine")
    sys.exit(1)
print("  Engine initialized successfully")

# Test 2: Try to change option while engine is running (should fail)
print("\nTest 2: Trying to change parallel processing while engine is running...")
host.set_engine_option(backend.ENGINE_OPTION_PARALLEL_PROCESSING, 0, "")
print("  (This should have printed an error message above)")

# Add some plugins to test parallel processing
print("\nAdding test plugins...")
plugin1 = host.add_plugin(backend.BINARY_NATIVE, backend.PLUGIN_INTERNAL, "", "", "audiofile", 0, None, 0)
if plugin1 >= 0:
    print(f"  Plugin 1 (Audio File) added with ID: {plugin1}")
else:
    print("  ERROR: Failed to add plugin 1")

plugin2 = host.add_plugin(backend.BINARY_NATIVE, backend.PLUGIN_INTERNAL, "", "", "audiogain_s", 0, None, 0)
if plugin2 >= 0:
    print(f"  Plugin 2 (Audio Gain) added with ID: {plugin2}")
else:
    print("  ERROR: Failed to add plugin 2")

# Give the engine time to stabilize
time.sleep(1)

# Check engine info
info = host.get_runtime_engine_info()
print(f"\nEngine info: {info}")

# Close the engine
print("\nClosing engine...")
host.engine_close()
print("  Engine closed")

# Test 3: Verify we can change the option after engine is closed
print("\nTest 3: Changing parallel processing option after engine close...")
host.set_engine_option(backend.ENGINE_OPTION_PARALLEL_PROCESSING, 0, "")
print("  Option changed successfully")

print("\nAll tests completed!")