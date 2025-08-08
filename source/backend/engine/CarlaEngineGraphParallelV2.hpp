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

#ifndef CARLA_ENGINE_GRAPH_PARALLEL_V2_HPP_INCLUDED
#define CARLA_ENGINE_GRAPH_PARALLEL_V2_HPP_INCLUDED

#include "CarlaEngineGraph.hpp"
#include "CarlaEngineDependencyGraph.hpp"
#include "CarlaEngineThreadPool.hpp"
#include "CarlaEngineBufferPool.hpp"

#include <memory>
#include <atomic>

CARLA_BACKEND_START_NAMESPACE

// -----------------------------------------------------------------------
// Modern parallel rack graph using C++20 features

class ParallelRackGraphV2 : public RackGraph {
public:
    ParallelRackGraphV2(CarlaEngine* engine, uint32_t inputs, uint32_t outputs) noexcept;
    ~ParallelRackGraphV2() noexcept;
    
    // Process method - we'll use the engine directly
    void processParallel(CarlaEngine* engine, 
                        const float* const* inBuf, 
                        float* const* outBuf, 
                        uint32_t frames);
    
    // Plugin management (not virtual in base class)
    void addPlugin(CarlaPluginPtr plugin);
    void removePlugin(CarlaPluginPtr plugin);
    void removeAllPlugins();
    
    // Performance monitoring
    void printPerformanceStats() const noexcept;
    
private:
    // Core components
    std::unique_ptr<CarlaEngineDependencyGraph> fDependencyGraph;
    std::unique_ptr<CarlaEngineThreadPool> fThreadPool;
    std::unique_ptr<CarlaEngineBufferPool> fBufferPool;
    
    // Configuration
    uint32_t fNumInputs;
    uint32_t fNumOutputs;
    uint32_t fBufferSize;
    
    // Performance tracking
    std::atomic<uint64_t> fTotalProcessTime{0};
    std::atomic<uint64_t> fProcessCount{0};
    std::atomic<uint64_t> fPeakProcessTime{0};
    
    // Internal methods
    void rebuildGraph() noexcept;
    void processLayer(const ExecutionLayer* layer, 
                     CarlaEngine* engine,
                     const float* const* inBuf,
                     float* const* outBuf,
                     uint32_t frames) noexcept;
    
    CARLA_DECLARE_NON_COPYABLE(ParallelRackGraphV2)
};

CARLA_BACKEND_END_NAMESPACE

#endif // CARLA_ENGINE_GRAPH_PARALLEL_V2_HPP_INCLUDED