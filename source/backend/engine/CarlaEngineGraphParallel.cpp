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

#include "CarlaEngineGraphParallel.hpp"
#include "CarlaEngineInternal.hpp"
#include "CarlaPlugin.hpp"
#include "CarlaUtils.hpp"

#include <cstring>
#include <thread>
#include <chrono>

CARLA_BACKEND_START_NAMESPACE

// -----------------------------------------------------------------------
// ParallelRackGraph

ParallelRackGraph::ParallelRackGraph(CarlaEngine* engine, uint32_t inputs, uint32_t outputs) noexcept
    : RackGraph(engine, inputs, outputs),
      fBufferSize(0),
      fThreadsRunning(false),
      fWorkersComplete(0)
{
    // Initialize worker thread pointers
    for (int i = 0; i < kNumWorkers; ++i)
    {
        fWorkers[i] = nullptr;
        fParallelInBuf[i][0] = nullptr;
        fParallelInBuf[i][1] = nullptr;
        fParallelOutBuf[i][0] = nullptr;
        fParallelOutBuf[i][1] = nullptr;
    }
}

ParallelRackGraph::~ParallelRackGraph() noexcept
{
    stopThreads();
    freeBuffers();
}

void ParallelRackGraph::allocateBuffers(uint32_t bufferSize)
{
    if (fBufferSize == bufferSize)
        return;
    
    freeBuffers();
    fBufferSize = bufferSize;
    
    // Allocate stereo buffers for each worker
    for (int i = 0; i < kNumWorkers; ++i)
    {
        fParallelInBuf[i][0] = new float[bufferSize];
        fParallelInBuf[i][1] = new float[bufferSize];
        fParallelOutBuf[i][0] = new float[bufferSize];
        fParallelOutBuf[i][1] = new float[bufferSize];
        
        // Clear buffers
        std::memset(fParallelInBuf[i][0], 0, sizeof(float) * bufferSize);
        std::memset(fParallelInBuf[i][1], 0, sizeof(float) * bufferSize);
        std::memset(fParallelOutBuf[i][0], 0, sizeof(float) * bufferSize);
        std::memset(fParallelOutBuf[i][1], 0, sizeof(float) * bufferSize);
    }
}

void ParallelRackGraph::freeBuffers()
{
    for (int i = 0; i < kNumWorkers; ++i)
    {
        delete[] fParallelInBuf[i][0];
        delete[] fParallelInBuf[i][1];
        delete[] fParallelOutBuf[i][0];
        delete[] fParallelOutBuf[i][1];
        
        fParallelInBuf[i][0] = nullptr;
        fParallelInBuf[i][1] = nullptr;
        fParallelOutBuf[i][0] = nullptr;
        fParallelOutBuf[i][1] = nullptr;
    }
    
    fBufferSize = 0;
}

bool ParallelRackGraph::startThreads()
{
    if (fThreadsRunning)
        return true;
    
    carla_stdout("Starting parallel processing threads...");
    
    // Create and start worker threads
    for (int i = 0; i < kNumWorkers; ++i)
    {
        fWorkers[i] = new WorkerThread(this, i);
        fWorkers[i]->startThread();
    }
    
    fThreadsRunning = true;
    return true;
}

void ParallelRackGraph::stopThreads()
{
    if (!fThreadsRunning)
        return;
    
    carla_stdout("Stopping parallel processing threads...");
    
    fThreadsRunning = false;
    
    // Signal all workers to stop
    for (int i = 0; i < kNumWorkers; ++i)
    {
        if (fWorkers[i] != nullptr)
        {
            fWorkers[i]->workData.ready = true;
            fWorkers[i]->signalThreadShouldExit();
        }
    }
    
    // Stop and delete worker threads
    for (int i = 0; i < kNumWorkers; ++i)
    {
        if (fWorkers[i] != nullptr)
        {
            fWorkers[i]->stopThread(5000);
            delete fWorkers[i];
            fWorkers[i] = nullptr;
        }
    }
}

void ParallelRackGraph::processParallel(CarlaEngine* engine, 
                                       const float* inBuf[], 
                                       float* outBuf[], 
                                       const uint32_t frames,
                                       const uint32_t channels)
{
    CARLA_SAFE_ASSERT_RETURN(engine != nullptr,);
    
    const uint32_t pluginCount = engine->getCurrentPluginCount();
    CARLA_SAFE_ASSERT_RETURN(pluginCount <= 3,);
    
    // Ensure buffers are allocated
    allocateBuffers(frames);
    
    // If threads aren't running or we have no plugins, return
    if (!fThreadsRunning || pluginCount == 0)
    {
        return;
    }
    
    // For POC: Only handle exactly 3 plugins in parallel
    if (pluginCount != 3)
    {
        return;
    }
    
    // Clear output buffers first
    std::memset(outBuf[0], 0, sizeof(float) * frames);
    std::memset(outBuf[1], 0, sizeof(float) * frames);
    
    // Prepare work for each thread
    fWorkersComplete = 0;
    
    for (uint i = 0; i < 3; ++i)
    {
        const CarlaPluginPtr plugin = engine->getPlugin(i);
        if (!plugin || !plugin->isEnabled())
            continue;
        
        // Copy input to worker's buffer (assuming 3 stereo inputs)
        if (i < 3 && inBuf[i*2] && inBuf[i*2+1])
        {
            std::memcpy(fParallelInBuf[i][0], inBuf[i*2], sizeof(float) * frames);
            std::memcpy(fParallelInBuf[i][1], inBuf[i*2+1], sizeof(float) * frames);
        }
        else
        {
            // Use first input if not enough inputs
            std::memcpy(fParallelInBuf[i][0], inBuf[0], sizeof(float) * frames);
            std::memcpy(fParallelInBuf[i][1], inBuf[1], sizeof(float) * frames);
        }
        
        // Set up work data
        fWorkers[i]->workData.plugin = plugin;
        fWorkers[i]->workData.inBuf = const_cast<const float**>(fParallelInBuf[i]);
        fWorkers[i]->workData.outBuf = fParallelOutBuf[i];
        fWorkers[i]->workData.cvBuf = nullptr;  // No CV for POC
        fWorkers[i]->workData.frames = frames;
        fWorkers[i]->workData.done = false;
        
        // Signal worker to start
        fWorkers[i]->workData.ready = true;
    }
    
    // Wait for all workers to complete
    while (fWorkersComplete < 3)
    {
        std::this_thread::yield();  // Yield to other threads
    }
    
    // Merge outputs from all workers
    for (uint i = 0; i < 3; ++i)
    {
        for (uint32_t j = 0; j < frames; ++j)
        {
            outBuf[0][j] += fParallelOutBuf[i][0][j] * 0.333f;  // Mix 1/3 each
            outBuf[1][j] += fParallelOutBuf[i][1][j] * 0.333f;
        }
    }
}

// -----------------------------------------------------------------------
// WorkerThread

ParallelRackGraph::WorkerThread::WorkerThread(ParallelRackGraph* graph, int id) noexcept
    : CarlaThread("ParallelWorker"),
      fGraph(graph),
      fId(id)
{
    workData.ready = false;
    workData.done = false;
}

void ParallelRackGraph::WorkerThread::run()
{
    carla_stdout("Worker thread %d started", fId);
    
    while (!shouldThreadExit())
    {
        // Wait for work
        if (!workData.ready)
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            continue;
        }
        
        // Process plugin
        if (workData.plugin && workData.plugin->isEnabled())
        {
            // Cast to proper types for plugin API
            float** outBufPtr = const_cast<float**>(workData.outBuf);
            float** cvBufPtr = workData.cvBuf ? const_cast<float**>(workData.cvBuf) : nullptr;
            
            workData.plugin->process(workData.inBuf, outBufPtr, 
                                   workData.cvBuf, cvBufPtr, 
                                   workData.frames);
        }
        
        // Mark as complete
        workData.done = true;
        workData.ready = false;
        fGraph->fWorkersComplete++;
    }
    
    carla_stdout("Worker thread %d stopped", fId);
}

// -----------------------------------------------------------------------

CARLA_BACKEND_END_NAMESPACE