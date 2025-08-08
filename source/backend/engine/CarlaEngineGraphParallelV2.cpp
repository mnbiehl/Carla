/*
 * Carla Plugin Host
 * Copyright (C) 2011-2025 Filipe Coelho <falktx@falktx.com>
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 of
 * the License, or any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * For a full copy of the GNU General Public License see the doc/GPL.txt file.
 */

#include "CarlaEngineGraphParallelV2.hpp"
#include "CarlaEngineInternal.hpp"
#include "CarlaPlugin.hpp"

#include <chrono>

CARLA_BACKEND_START_NAMESPACE

// -----------------------------------------------------------------------
// ParallelRackGraphV2

ParallelRackGraphV2::ParallelRackGraphV2(CarlaEngine* engine, uint32_t inputs, uint32_t outputs) noexcept
    : RackGraph(engine, inputs, outputs)
    , fNumInputs(inputs)
    , fNumOutputs(outputs)
    , fBufferSize(engine->getBufferSize())
{
    carla_debug("ParallelRackGraphV2::ParallelRackGraphV2(%p, %u, %u)", engine, inputs, outputs);
    
    // Initialize dependency graph
    fDependencyGraph = std::make_unique<CarlaEngineDependencyGraph>();
    
    // Create thread pool with optimal worker count
    const uint numCores = std::thread::hardware_concurrency();
    const uint numWorkers = std::min(numCores, 8u);  // Cap at 8 workers for audio
    const uint numRealtimeWorkers = std::min(numCores / 2, 4u);  // Half for RT
    
    fThreadPool = std::make_unique<CarlaEngineThreadPool>(numWorkers, numRealtimeWorkers);
    fThreadPool->start();
    
    // Create buffer pool with enough buffers for parallel processing
    const uint buffersPerPlugin = 4;  // 2 input + 2 output channels
    const uint maxPlugins = 64;
    const uint numBuffers = maxPlugins * buffersPerPlugin;
    
    fBufferPool = std::make_unique<CarlaEngineBufferPool>(fBufferSize, numBuffers);
    
    carla_stdout("ParallelRackGraphV2: Created with %u workers, %u RT workers, %u buffers",
                numWorkers, numRealtimeWorkers, numBuffers);
}

ParallelRackGraphV2::~ParallelRackGraphV2() noexcept
{
    carla_debug("ParallelRackGraphV2::~ParallelRackGraphV2()");
    
    if (fProcessCount > 0)
    {
        const uint64_t avgTime = fTotalProcessTime / fProcessCount;
        carla_stdout("ParallelRackGraphV2: Performance stats:");
        carla_stdout("  Total process calls: %lu", fProcessCount.load());
        carla_stdout("  Average process time: %lu µs", avgTime);
        carla_stdout("  Peak process time: %lu µs", fPeakProcessTime.load());
        carla_stdout("  Buffer pool peak usage: %u/%u",
                    fBufferPool->getPeakAllocated(), fBufferPool->getNumBuffers());
    }
    
    // Stop thread pool before destruction
    if (fThreadPool)
        fThreadPool->stop();
}

void ParallelRackGraphV2::process(CarlaEngine::ProtectedData* data,
                                  const float* inBuf[],
                                  float* outBuf[],
                                  uint32_t frames,
                                  uint32_t channels)
{
    CARLA_SAFE_ASSERT_RETURN(data != nullptr,);
    CarlaEngine* const engine = kEngine;
    CARLA_SAFE_ASSERT_RETURN(frames > 0,);
    
    auto startTime = std::chrono::high_resolution_clock::now();
    
    // Clear output buffers first
    for (uint32_t i = 0; i < fNumOutputs; ++i)
    {
        if (outBuf[i] != nullptr)
            carla_zeroFloats(outBuf[i], frames);
    }
    
    // Get the execution layers from dependency graph
    const auto& layers = fDependencyGraph->getLayers();
    
    if (layers.empty())
    {
        // No plugins or graph not analyzed yet
        // Just copy input to output
        const uint32_t numCopy = std::min(fNumInputs, fNumOutputs);
        for (uint32_t i = 0; i < numCopy; ++i)
        {
            if (inBuf[i] != nullptr && outBuf[i] != nullptr)
                carla_copyFloats(outBuf[i], inBuf[i], frames);
        }
        return;
    }
    
    // Process each layer in sequence (layers can run in parallel)
    for (const auto& layer : layers)
    {
        processLayer(&layer, engine, inBuf, outBuf, frames);
    }
    
    // Update performance metrics
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(endTime - startTime);
    
    uint64_t processTime = duration.count();
    fTotalProcessTime.fetch_add(processTime);
    fProcessCount.fetch_add(1);
    
    // Update peak time
    uint64_t currentPeak = fPeakProcessTime.load();
    while (processTime > currentPeak && 
           !fPeakProcessTime.compare_exchange_weak(currentPeak, processTime))
        ;
}

void ParallelRackGraphV2::processLayer(const ExecutionLayer* layer,
                                       CarlaEngine* engine,
                                       const float* const* inBuf,
                                       float* const* outBuf,
                                       uint32_t frames) noexcept
{
    if (layer == nullptr || layer->pluginIds.empty())
        return;
    
    // If only one plugin in layer, process directly without threading overhead
    if (layer->pluginIds.size() == 1)
    {
        const uint pluginId = layer->pluginIds[0];
        CarlaPluginPtr plugin = engine->getPlugin(pluginId);
        
        if (plugin != nullptr && plugin->isEnabled())
        {
            // Get buffers from pool
            CarlaEngineBufferPool::ScopedBuffer inBuffer1(*fBufferPool);
            CarlaEngineBufferPool::ScopedBuffer inBuffer2(*fBufferPool);
            CarlaEngineBufferPool::ScopedBuffer outBuffer1(*fBufferPool);
            CarlaEngineBufferPool::ScopedBuffer outBuffer2(*fBufferPool);
            
            if (!inBuffer1.isValid() || !inBuffer2.isValid() ||
                !outBuffer1.isValid() || !outBuffer2.isValid())
            {
                carla_stderr2("Failed to acquire buffers for plugin %u", pluginId);
                return;
            }
            
            // Copy input data
            if (pluginId == 0 && inBuf != nullptr)
            {
                // First plugin gets actual input
                if (fNumInputs > 0 && inBuf[0] != nullptr)
                    inBuffer1->copyFrom(inBuf[0], frames);
                if (fNumInputs > 1 && inBuf[1] != nullptr)
                    inBuffer2->copyFrom(inBuf[1], frames);
            }
            
            // Process plugin
            float* pluginInBuf[2] = { inBuffer1->getData(), inBuffer2->getData() };
            float* pluginOutBuf[2] = { outBuffer1->getData(), outBuffer2->getData() };
            
            auto procStart = std::chrono::high_resolution_clock::now();
            // CV buffers are nullptr for rack mode
            plugin->process(const_cast<const float**>(pluginInBuf), pluginOutBuf, 
                          nullptr, nullptr, frames);
            auto procEnd = std::chrono::high_resolution_clock::now();
            
            auto procTime = std::chrono::duration_cast<std::chrono::microseconds>(procEnd - procStart);
            fDependencyGraph->updatePluginProcessTime(pluginId, procTime.count());
            
            // Mix to output if this is a final plugin
            const auto& dependents = fDependencyGraph->getPluginDependents(pluginId);
            if (dependents.empty() && outBuf != nullptr)
            {
                // This plugin has no dependents, mix to main output
                if (fNumOutputs > 0 && outBuf[0] != nullptr)
                    outBuffer1->copyTo(outBuf[0], frames);
                if (fNumOutputs > 1 && outBuf[1] != nullptr)
                    outBuffer2->copyTo(outBuf[1], frames);
            }
        }
        return;
    }
    
    // Multiple plugins - process in parallel
    std::vector<Task> layerTasks;
    layerTasks.reserve(layer->pluginIds.size());
    
    for (uint pluginId : layer->pluginIds)
    {
        layerTasks.push_back([this, engine, pluginId, inBuf, outBuf, frames]() {
            CarlaPluginPtr plugin = engine->getPlugin(pluginId);
            
            if (plugin == nullptr || !plugin->isEnabled())
                return;
            
            // Get buffers from pool
            CarlaEngineBufferPool::ScopedBuffer inBuffer1(*fBufferPool);
            CarlaEngineBufferPool::ScopedBuffer inBuffer2(*fBufferPool);
            CarlaEngineBufferPool::ScopedBuffer outBuffer1(*fBufferPool);
            CarlaEngineBufferPool::ScopedBuffer outBuffer2(*fBufferPool);
            
            if (!inBuffer1.isValid() || !inBuffer2.isValid() ||
                !outBuffer1.isValid() || !outBuffer2.isValid())
            {
                carla_stderr2("Failed to acquire buffers for plugin %u", pluginId);
                return;
            }
            
            // Setup input buffers based on dependencies
            const auto& dependencies = fDependencyGraph->getPluginDependencies(pluginId);
            if (dependencies.empty() && pluginId == 0 && inBuf != nullptr)
            {
                // First plugin with no dependencies gets actual input
                if (fNumInputs > 0 && inBuf[0] != nullptr)
                    inBuffer1->copyFrom(inBuf[0], frames);
                if (fNumInputs > 1 && inBuf[1] != nullptr)
                    inBuffer2->copyFrom(inBuf[1], frames);
            }
            else
            {
                // TODO: Get input from dependent plugins' outputs
                // This requires inter-plugin buffer management
            }
            
            // Process plugin
            float* pluginInBuf[2] = { inBuffer1->getData(), inBuffer2->getData() };
            float* pluginOutBuf[2] = { outBuffer1->getData(), outBuffer2->getData() };
            
            auto procStart = std::chrono::high_resolution_clock::now();
            // CV buffers are nullptr for rack mode
            plugin->process(const_cast<const float**>(pluginInBuf), pluginOutBuf, 
                          nullptr, nullptr, frames);
            auto procEnd = std::chrono::high_resolution_clock::now();
            
            auto procTime = std::chrono::duration_cast<std::chrono::microseconds>(procEnd - procStart);
            fDependencyGraph->updatePluginProcessTime(pluginId, procTime.count());
            
            // Mix to output if this is a final plugin
            const auto& dependents = fDependencyGraph->getPluginDependents(pluginId);
            if (dependents.empty() && outBuf != nullptr)
            {
                // This plugin has no dependents, mix to main output
                // Use atomic operations or mutex for thread-safe mixing
                static std::mutex outputMutex;
                std::lock_guard<std::mutex> lock(outputMutex);
                
                if (fNumOutputs > 0 && outBuf[0] != nullptr)
                {
                    for (uint32_t i = 0; i < frames; ++i)
                        outBuf[0][i] += pluginOutBuf[0][i];
                }
                if (fNumOutputs > 1 && outBuf[1] != nullptr)
                {
                    for (uint32_t i = 0; i < frames; ++i)
                        outBuf[1][i] += pluginOutBuf[1][i];
                }
            }
        });
    }
    
    // Execute all plugins in this layer in parallel and wait for completion
    fThreadPool->executeParallelGroup(layerTasks);
}

void ParallelRackGraphV2::addPlugin(CarlaPluginPtr plugin)
{
    CARLA_SAFE_ASSERT_RETURN(plugin != nullptr,);
    
    const uint pluginId = plugin->getId();
    
    carla_debug("ParallelRackGraphV2::addPlugin(%u)", pluginId);
    
    // Add to dependency graph
    // Note: We need the actual CarlaEngineClient pointer
    // For now, we'll use the plugin pointer as a placeholder
    fDependencyGraph->addPlugin(pluginId, nullptr);
    
    // Rebuild the graph
    rebuildGraph();
}

void ParallelRackGraphV2::removePlugin(CarlaPluginPtr plugin)
{
    CARLA_SAFE_ASSERT_RETURN(plugin != nullptr,);
    
    const uint pluginId = plugin->getId();
    
    carla_debug("ParallelRackGraphV2::removePlugin(%u)", pluginId);
    
    // Remove from dependency graph
    fDependencyGraph->removePlugin(pluginId);
    

    
    // Rebuild the graph
    rebuildGraph();
}

void ParallelRackGraphV2::removeAllPlugins()
{
    carla_debug("ParallelRackGraphV2::removeAllPlugins()");
    
    // Clear dependency graph
    fDependencyGraph->clear();
    

}

bool ParallelRackGraphV2::connect(uint groupA, uint portA, uint groupB, uint portB) noexcept
{
    carla_debug("ParallelRackGraphV2::connect(%u:%u -> %u:%u)", groupA, portA, groupB, portB);
    
    // Call base class connect method
    if (!RackGraph::connect(groupA, portA, groupB, portB))
        return false;
    
    // Add connection to dependency graph
    // Note: In rack mode, plugins are connected in series
    // groupA and groupB represent plugin IDs
    fDependencyGraph->addConnection(groupA, portA, groupB, portB);
    
    // Rebuild the graph
    rebuildGraph();
    
    return true;
}

bool ParallelRackGraphV2::disconnect(uint connectionId) noexcept
{
    carla_debug("ParallelRackGraphV2::disconnect(%u)", connectionId);
    
    // Call base class disconnect method
    if (!RackGraph::disconnect(connectionId))
        return false;
    
    // TODO: Remove connection from dependency graph
    // This requires tracking connection IDs
    
    // Rebuild the graph
    rebuildGraph();
    
    return true;
}

void ParallelRackGraphV2::setBufferSize(uint32_t bufferSize)
{
    carla_debug("ParallelRackGraphV2::setBufferSize(%u)", bufferSize);
    
    if (fBufferSize == bufferSize)
        return;
    
    fBufferSize = bufferSize;
    
    // Recreate buffer pool with new size
    const uint buffersPerPlugin = 4;
    const uint maxPlugins = 64;
    const uint numBuffers = maxPlugins * buffersPerPlugin;
    
    fBufferPool = std::make_unique<CarlaEngineBufferPool>(bufferSize, numBuffers);
    
    // Call base class setBufferSize
    RackGraph::setBufferSize(bufferSize);
}

void ParallelRackGraphV2::rebuildGraph() noexcept
{
    carla_debug("ParallelRackGraphV2::rebuildGraph()");
    
    // Analyze the dependency graph
    bool noCycles = fDependencyGraph->analyze();
    
    if (!noCycles)
    {
        carla_stderr2("Warning: Cycle detected in plugin graph!");
        carla_stderr2("Parallel processing may not work correctly with feedback loops.");
    }
    
    // Print the execution order for debugging
    if (fDependencyGraph->getNumLayers() > 0)
    {
        carla_stdout("Plugin execution order (%u layers):", fDependencyGraph->getNumLayers());
        fDependencyGraph->printExecutionOrder();
    }
}

void ParallelRackGraphV2::printPerformanceStats() const noexcept
{
    if (fProcessCount == 0)
    {
        carla_stdout("No processing statistics available yet");
        return;
    }
    
    const uint64_t avgTime = fTotalProcessTime / fProcessCount;
    
    carla_stdout("=== ParallelRackGraphV2 Performance Stats ===");
    carla_stdout("Process calls: %lu", fProcessCount.load());
    carla_stdout("Average time: %lu µs", avgTime);
    carla_stdout("Peak time: %lu µs", fPeakProcessTime.load());
    carla_stdout("Buffer pool peak: %u/%u", 
                fBufferPool->getPeakAllocated(), fBufferPool->getNumBuffers());
    carla_stdout("Thread pool: %u workers, %u RT workers",
                fThreadPool->getNumWorkers(), fThreadPool->getNumRealtimeWorkers());
    
    // Print per-plugin stats
    carla_stdout("\nPer-plugin processing times:");
    fDependencyGraph->printExecutionOrder();
}

CARLA_BACKEND_END_NAMESPACE