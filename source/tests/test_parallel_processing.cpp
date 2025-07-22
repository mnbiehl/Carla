/*
 * Test for Parallel Plugin Processing
 */

#include "CarlaEngineGraphParallel.hpp"
#include "CarlaEngine.hpp"
#include "CarlaPlugin.hpp"
#include <cstdio>
#include <chrono>

CARLA_BACKEND_USE_NAMESPACE

int main()
{
    printf("=== Parallel Plugin Processing Test ===\n");
    
    // Create engine
    CarlaEngine* engine = CarlaEngine::newDriverByName("Dummy");
    if (!engine)
    {
        printf("Failed to create engine\n");
        return 1;
    }
    
    // Initialize engine
    if (!engine->init("Parallel Test"))
    {
        printf("Failed to initialize engine\n");
        delete engine;
        return 1;
    }
    
    // Set buffer size
    engine->setOption(ENGINE_OPTION_AUDIO_BUFFER_SIZE, 512, nullptr);
    
    // Create parallel rack graph with 6 inputs (3 stereo) and 2 outputs (1 stereo)
    ParallelRackGraph* graph = new ParallelRackGraph(engine, 6, 2);
    
    // Start worker threads
    if (!graph->startThreads())
    {
        printf("Failed to start worker threads\n");
        delete graph;
        delete engine;
        return 1;
    }
    
    printf("Worker threads started successfully\n");
    
    // TODO: Add 3 test plugins and measure performance
    // For now, just test thread creation/destruction
    
    // Test processing with dummy buffers
    const uint32_t frames = 512;
    float inBuf[6][frames];  // 3 stereo inputs
    float outBuf[2][frames]; // 1 stereo output
    
    float* inPtrs[6];
    float* outPtrs[2];
    
    for (int i = 0; i < 6; ++i)
        inPtrs[i] = inBuf[i];
    for (int i = 0; i < 2; ++i)
        outPtrs[i] = outBuf[i];
    
    // Fill input with test signal
    for (int i = 0; i < 6; ++i)
    {
        for (uint32_t j = 0; j < frames; ++j)
            inBuf[i][j] = 0.1f;
    }
    
    // Process
    printf("Testing process() call...\n");
    
    auto start = std::chrono::high_resolution_clock::now();
    
    // Process multiple times to measure performance
    for (int i = 0; i < 100; ++i)
    {
        graph->processParallel(engine, 
                              (const float**)inPtrs, 
                              outPtrs, 
                              frames);
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
    
    printf("Processed 100 buffers in %ld microseconds\n", duration.count());
    printf("Average per buffer: %ld microseconds\n", duration.count() / 100);
    
    // Stop threads
    graph->stopThreads();
    
    // Cleanup
    delete graph;
    delete engine;
    
    printf("Test completed successfully\n");
    return 0;
}