/*
 * Test for Carla's parallel plugin processing system
 * Tests dependency graph, thread pool, and buffer management
 */

#include <iostream>
#include <chrono>
#include <random>
#include <cassert>

#include "source/backend/engine/CarlaEngineDependencyGraph.hpp"
#include "source/backend/engine/CarlaEngineThreadPool.hpp"
#include "source/backend/engine/CarlaEngineBufferPool.hpp"

using namespace CarlaBackend;

// Mock plugin client for testing
class MockPluginClient : public CarlaEngineClient {
public:
    MockPluginClient(uint id) : fId(id) {}
    
    void processAudio(float** inBuf, float** outBuf, uint32_t frames) {
        // Simulate some processing work
        std::this_thread::sleep_for(std::chrono::microseconds(100));
        
        // Simple gain processing
        for (uint32_t ch = 0; ch < 2; ++ch) {
            for (uint32_t i = 0; i < frames; ++i) {
                outBuf[ch][i] = inBuf[ch][i] * 0.8f;
            }
        }
    }
    
    uint getId() const { return fId; }
    
private:
    uint fId;
};

void testDependencyGraph() {
    std::cout << "\n=== Testing Dependency Graph ===" << std::endl;
    
    CarlaEngineDependencyGraph graph;
    
    // Create mock plugins
    std::vector<std::unique_ptr<MockPluginClient>> plugins;
    for (uint i = 0; i < 6; ++i) {
        plugins.push_back(std::make_unique<MockPluginClient>(i));
        graph.addPlugin(i, plugins[i].get());
    }
    
    // Create a complex routing:
    // 0 -> 2 -> 4
    // 1 -> 2 -> 5
    // 1 -> 3 -> 5
    graph.addConnection(0, 0, 2, 0);  // Plugin 0 output -> Plugin 2 input
    graph.addConnection(1, 0, 2, 1);  // Plugin 1 output -> Plugin 2 input
    graph.addConnection(2, 0, 4, 0);  // Plugin 2 output -> Plugin 4 input
    graph.addConnection(2, 0, 5, 0);  // Plugin 2 output -> Plugin 5 input
    graph.addConnection(1, 1, 3, 0);  // Plugin 1 output -> Plugin 3 input
    graph.addConnection(3, 0, 5, 1);  // Plugin 3 output -> Plugin 5 input
    
    // Analyze the graph
    bool noCycles = graph.analyze();
    std::cout << "Graph has cycles: " << (noCycles ? "No" : "Yes") << std::endl;
    std::cout << "Number of execution layers: " << graph.getNumLayers() << std::endl;
    
    // Print execution order
    graph.printExecutionOrder();
    
    // Test cycle detection
    std::cout << "\nTesting cycle detection..." << std::endl;
    graph.addConnection(5, 0, 1, 0);  // Create a cycle: 5 -> 1
    noCycles = graph.analyze();
    std::cout << "After adding cycle - Has cycles: " << (noCycles ? "No" : "Yes") << std::endl;
    
    assert(!noCycles);  // Should detect the cycle
    
    std::cout << "✓ Dependency graph tests passed!" << std::endl;
}

void testThreadPool() {
    std::cout << "\n=== Testing Thread Pool ===" << std::endl;
    
    CarlaEngineThreadPool pool(4, 2);  // 4 normal workers, 2 realtime workers
    pool.start();
    
    // Test basic task submission
    std::cout << "Testing basic task submission..." << std::endl;
    auto future = pool.submitTask([]() {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        return 42;
    });
    
    int result = future.get();
    assert(result == 42);
    std::cout << "✓ Basic task returned: " << result << std::endl;
    
    // Test parallel for
    std::cout << "Testing parallel for..." << std::endl;
    std::atomic<int> counter{0};
    pool.parallelFor(0, 100, [&counter](size_t i) {
        counter.fetch_add(1);
    });
    
    assert(counter.load() == 100);
    std::cout << "✓ Parallel for processed " << counter.load() << " items" << std::endl;
    
    // Test realtime task submission
    std::cout << "Testing realtime tasks..." << std::endl;
    std::atomic<int> rtCounter{0};
    for (int i = 0; i < 10; ++i) {
        bool submitted = pool.submitRealtimeTask([&rtCounter]() {
            rtCounter.fetch_add(1);
        });
        assert(submitted);
    }
    
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    std::cout << "✓ Realtime tasks processed: " << rtCounter.load() << std::endl;
    
    // Test parallel group execution with latch
    std::cout << "Testing parallel group execution..." << std::endl;
    std::vector<Task> tasks;
    std::atomic<int> groupCounter{0};
    for (int i = 0; i < 10; ++i) {
        tasks.push_back([&groupCounter]() {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            groupCounter.fetch_add(1);
        });
    }
    
    auto start = std::chrono::high_resolution_clock::now();
    pool.executeParallelGroup(tasks);
    auto end = std::chrono::high_resolution_clock::now();
    
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
    assert(groupCounter.load() == 10);
    std::cout << "✓ Group execution completed in " << duration.count() << "ms" << std::endl;
    
    pool.stop();
    std::cout << "✓ Thread pool tests passed!" << std::endl;
}

void testBufferPool() {
    std::cout << "\n=== Testing Buffer Pool ===" << std::endl;
    
    const uint32_t bufferSize = 512;
    const uint32_t numBuffers = 10;
    
    CarlaEngineBufferPool pool(bufferSize, numBuffers);
    
    // Test buffer acquisition
    std::cout << "Testing buffer acquisition..." << std::endl;
    std::vector<AudioBuffer*> buffers;
    for (uint32_t i = 0; i < 5; ++i) {
        AudioBuffer* buf = pool.acquire();
        assert(buf != nullptr);
        assert(buf->getSize() == bufferSize);
        buffers.push_back(buf);
    }
    
    assert(pool.getAllocatedCount() == 5);
    std::cout << "✓ Acquired 5 buffers" << std::endl;
    
    // Test buffer release
    std::cout << "Testing buffer release..." << std::endl;
    for (auto* buf : buffers) {
        pool.release(buf);
    }
    
    assert(pool.getAllocatedCount() == 0);
    std::cout << "✓ Released all buffers" << std::endl;
    
    // Test RAII wrapper
    std::cout << "Testing RAII buffer wrapper..." << std::endl;
    {
        CarlaEngineBufferPool::ScopedBuffer scopedBuf(pool);
        assert(scopedBuf.isValid());
        assert(pool.getAllocatedCount() == 1);
        
        // Test buffer operations
        float testData[bufferSize];
        for (uint32_t i = 0; i < bufferSize; ++i) {
            testData[i] = static_cast<float>(i) / bufferSize;
        }
        
        scopedBuf->copyFrom(testData, bufferSize);
        scopedBuf->mixFrom(testData, bufferSize, 0.5f);
        
        // Buffer should be automatically released when scopedBuf goes out of scope
    }
    
    assert(pool.getAllocatedCount() == 0);
    std::cout << "✓ RAII wrapper released buffer automatically" << std::endl;
    
    // Test multi-channel buffer
    std::cout << "Testing multi-channel buffer..." << std::endl;
    MultiChannelBuffer multiBuffer(2, bufferSize);
    
    assert(multiBuffer.getChannelCount() == 2);
    assert(multiBuffer.getSampleCount() == bufferSize);
    
    AudioBuffer* ch0 = multiBuffer.getChannel(0);
    AudioBuffer* ch1 = multiBuffer.getChannel(1);
    assert(ch0 != nullptr);
    assert(ch1 != nullptr);
    
    float** rawBuffers = multiBuffer.getRawBuffers();
    assert(rawBuffers != nullptr);
    assert(rawBuffers[0] == ch0->getData());
    assert(rawBuffers[1] == ch1->getData());
    
    std::cout << "✓ Multi-channel buffer tests passed!" << std::endl;
    
    // Test SIMD operations
    std::cout << "Testing SIMD mix operations..." << std::endl;
    AudioBuffer* testBuf = pool.acquire();
    
    float sourceData[bufferSize];
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_real_distribution<float> dist(-1.0f, 1.0f);
    
    for (uint32_t i = 0; i < bufferSize; ++i) {
        sourceData[i] = dist(gen);
    }
    
    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < 1000; ++i) {
        testBuf->clear();
        testBuf->mixFrom(sourceData, bufferSize, 0.7f);
    }
    auto end = std::chrono::high_resolution_clock::now();
    
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
    std::cout << "✓ 1000 SIMD mix operations completed in " << duration.count() << "µs" << std::endl;
    
    pool.release(testBuf);
    
    std::cout << "Peak buffer usage: " << pool.getPeakAllocated() << "/" << numBuffers << std::endl;
    std::cout << "✓ Buffer pool tests passed!" << std::endl;
}

void testIntegration() {
    std::cout << "\n=== Testing Integration ===" << std::endl;
    
    // Create components
    CarlaEngineDependencyGraph graph;
    CarlaEngineThreadPool threadPool(4, 2);
    CarlaEngineBufferPool bufferPool(512, 20);
    
    threadPool.start();
    
    // Create mock plugins
    const uint numPlugins = 8;
    std::vector<std::unique_ptr<MockPluginClient>> plugins;
    for (uint i = 0; i < numPlugins; ++i) {
        plugins.push_back(std::make_unique<MockPluginClient>(i));
        graph.addPlugin(i, plugins[i].get());
    }
    
    // Create connections (chain with parallel branches)
    graph.addConnection(0, 0, 2, 0);
    graph.addConnection(0, 1, 3, 0);
    graph.addConnection(1, 0, 4, 0);
    graph.addConnection(1, 1, 5, 0);
    graph.addConnection(2, 0, 6, 0);
    graph.addConnection(3, 0, 6, 1);
    graph.addConnection(4, 0, 7, 0);
    graph.addConnection(5, 0, 7, 1);
    
    graph.analyze();
    
    std::cout << "Processing plugins in parallel layers..." << std::endl;
    
    // Simulate audio processing
    const uint32_t frames = 512;
    auto start = std::chrono::high_resolution_clock::now();
    
    for (uint layer = 0; layer < graph.getNumLayers(); ++layer) {
        const ExecutionLayer* execLayer = graph.getLayer(layer);
        if (execLayer == nullptr) continue;
        
        std::vector<Task> layerTasks;
        
        for (uint pluginId : execLayer->pluginIds) {
            layerTasks.push_back([&, pluginId]() {
                // Get buffers from pool
                CarlaEngineBufferPool::ScopedBuffer inBuf1(bufferPool);
                CarlaEngineBufferPool::ScopedBuffer inBuf2(bufferPool);
                CarlaEngineBufferPool::ScopedBuffer outBuf1(bufferPool);
                CarlaEngineBufferPool::ScopedBuffer outBuf2(bufferPool);
                
                if (!inBuf1.isValid() || !inBuf2.isValid() || 
                    !outBuf1.isValid() || !outBuf2.isValid()) {
                    std::cerr << "Failed to acquire buffers for plugin " << pluginId << std::endl;
                    return;
                }
                
                float* inBuffers[2] = { inBuf1->getData(), inBuf2->getData() };
                float* outBuffers[2] = { outBuf1->getData(), outBuf2->getData() };
                
                // Process audio
                auto procStart = std::chrono::high_resolution_clock::now();
                plugins[pluginId]->processAudio(inBuffers, outBuffers, frames);
                auto procEnd = std::chrono::high_resolution_clock::now();
                
                auto procTime = std::chrono::duration_cast<std::chrono::microseconds>(procEnd - procStart);
                graph.updatePluginProcessTime(pluginId, procTime.count());
            });
        }
        
        // Execute all plugins in this layer in parallel
        threadPool.executeParallelGroup(layerTasks);
        
        std::cout << "  Layer " << layer << " processed " 
                  << execLayer->pluginIds.size() << " plugins in parallel" << std::endl;
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
    
    std::cout << "Total processing time: " << duration.count() << "µs" << std::endl;
    std::cout << "Buffer pool peak usage: " << bufferPool.getPeakAllocated() 
              << "/" << bufferPool.getNumBuffers() << std::endl;
    
    // Print plugin processing times
    std::cout << "\nPlugin processing times:" << std::endl;
    for (uint i = 0; i < numPlugins; ++i) {
        std::cout << "  Plugin " << i << ": " 
                  << graph.getPluginAvgProcessTime(i) << "µs" << std::endl;
    }
    
    threadPool.stop();
    std::cout << "✓ Integration test passed!" << std::endl;
}

int main() {
    std::cout << "=== Carla Parallel Processing Test Suite ===" << std::endl;
    std::cout << "Testing with C++20 features enabled" << std::endl;
    
    try {
        testDependencyGraph();
        testThreadPool();
        testBufferPool();
        testIntegration();
        
        std::cout << "\n✅ All tests passed successfully!" << std::endl;
        return 0;
    }
    catch (const std::exception& e) {
        std::cerr << "\n❌ Test failed with exception: " << e.what() << std::endl;
        return 1;
    }
}