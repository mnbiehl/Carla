/*
 * Carla Plugin Host
 * Copyright (C) 2011-2023 Filipe Coelho <falktx@falktx.com>
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

#ifndef CARLA_ENGINE_GRAPH_PARALLEL_HPP_INCLUDED
#define CARLA_ENGINE_GRAPH_PARALLEL_HPP_INCLUDED

#include "CarlaEngineGraph.hpp"
#include "CarlaThread.hpp"
#include "CarlaUtils.hpp"
#include <atomic>
#include <array>

CARLA_BACKEND_START_NAMESPACE

// -----------------------------------------------------------------------
// Parallel Processing POC - Fixed 3 plugin parallel processing

class ParallelRackGraph : public RackGraph
{
public:
    ParallelRackGraph(CarlaEngine* engine, uint32_t inputs, uint32_t outputs) noexcept;
    ~ParallelRackGraph() noexcept;

    // Process method for parallel execution
    void processParallel(CarlaEngine* engine,
                        const float* inBuf[], 
                        float* outBuf[], 
                        uint32_t frames,
                        uint32_t channels = 2);

    // Start/stop worker threads
    bool startThreads();
    void stopThreads();

private:
    // Worker thread class
    class WorkerThread : public CarlaThread
    {
    public:
        WorkerThread(ParallelRackGraph* graph, int id) noexcept;
        
        // Thread work data
        struct WorkData {
            CarlaPluginPtr plugin;
            float const* const* inBuf;
            float* const* outBuf;
            float* const* cvBuf;
            uint32_t frames;
            std::atomic<bool> ready;
            std::atomic<bool> done;
        };
        
        WorkData workData;
        
    private:
        ParallelRackGraph* const fGraph;
        const int fId;
        
        void run() override;
    };
    
    // Fixed 3 worker threads for POC
    static constexpr int kNumWorkers = 3;
    std::array<WorkerThread*, kNumWorkers> fWorkers;
    
    // Temporary buffers for parallel processing
    float* fParallelInBuf[kNumWorkers][2];   // Stereo input buffers
    float* fParallelOutBuf[kNumWorkers][2];  // Stereo output buffers
    
    // Buffer size tracking
    uint32_t fBufferSize;
    
    // Thread synchronization
    std::atomic<bool> fThreadsRunning;
    std::atomic<int> fWorkersComplete;
    
    // Allocate/free buffers
    void allocateBuffers(uint32_t bufferSize);
    void freeBuffers();
    
    CARLA_DECLARE_NON_COPYABLE(ParallelRackGraph)
};

// -----------------------------------------------------------------------

CARLA_BACKEND_END_NAMESPACE

#endif // CARLA_ENGINE_GRAPH_PARALLEL_HPP_INCLUDED