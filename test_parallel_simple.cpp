/*
 * Simple test for Carla's parallel processing components
 */

#include <iostream>
#include <chrono>
#include <random>
#include <cassert>
#include <cstring>

// Include only the components we can test independently
#include "source/backend/engine/CarlaEngineThreadPool.hpp"
#include "source/backend/engine/CarlaEngineBufferPool.hpp"

using namespace CarlaBackend;

void testThreadPool() {
    std::cout << "\n=== Testing Thread Pool with C++20 ===" << std::endl;
    
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
    
    // Test C++20 latch-based parallel group execution
    std::cout << "Testing C++20 latch-based parallel group..." << std::endl;
    std::vector<Task> tasks;
    std::atomic<int> groupCounter{0};
    for (int i = 0; i < 10; ++i) {
        tasks.push_back([&groupCounter, i]() {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            groupCounter.fetch_add(1);
            std::cout << "  Task " << i << " completed on thread " 
                      << std::this_thread::get_id() << std::endl;
        });
    }
    
    auto start = std::chrono::high_resolution_clock::now();
    pool.executeParallelGroup(tasks);
    auto end = std::chrono::high_resolution_clock::now();
    
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
    assert(groupCounter.load() == 10);
    std::cout << "✓ Group execution completed in " << duration.count() << "ms" << std::endl;
    
    // Test C++20 barrier synchronization
    std::cout << "Testing C++20 barrier synchronization..." << std::endl;
    std::atomic<int> barrierCounter{0};
    std::atomic<bool> completionCalled{false};
    
    std::vector<Task> barrierTasks;
    for (int i = 0; i < 5; ++i) {
        barrierTasks.push_back([&barrierCounter, i]() {
            std::cout << "  Barrier task " << i << " starting" << std::endl;
            std::this_thread::sleep_for(std::chrono::milliseconds(10 * (i + 1)));
            barrierCounter.fetch_add(1);
            std::cout << "  Barrier task " << i << " at barrier" << std::endl;
        });
    }
    
    pool.executeWithBarrier(barrierTasks, [&completionCalled]() {
        completionCalled.store(true);
        std::cout << "  All tasks reached barrier - completion callback executed!" << std::endl;
    });
    
    assert(barrierCounter.load() == 5);
    assert(completionCalled.load());
    std::cout << "✓ Barrier synchronization completed successfully" << std::endl;
    
    pool.stop();
    std::cout << "✓ Thread pool tests passed!" << std::endl;
}

void testBufferPool() {
    std::cout << "\n=== Testing Buffer Pool with SIMD ===" << std::endl;
    
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
    
    // Test RAII wrapper with C++20 features
    std::cout << "Testing RAII buffer wrapper..." << std::endl;
    {
        CarlaEngineBufferPool::ScopedBuffer scopedBuf(pool);
        assert(scopedBuf.isValid());
        assert(pool.getAllocatedCount() == 6);
        
        // Test buffer operations
        float testData[bufferSize];
        for (uint32_t i = 0; i < bufferSize; ++i) {
            testData[i] = static_cast<float>(i) / bufferSize;
        }
        
        scopedBuf->copyFrom(testData, bufferSize);
        scopedBuf->mixFrom(testData, bufferSize, 0.5f);
    }
    
    assert(pool.getAllocatedCount() == 5);
    std::cout << "✓ RAII wrapper released buffer automatically" << std::endl;
    
    // Release all buffers
    for (auto* buf : buffers) {
        pool.release(buf);
    }
    
    // Benchmark SIMD operations
    std::cout << "\nBenchmarking SIMD operations..." << std::endl;
    AudioBuffer* testBuf = pool.acquire();
    
    float sourceData[bufferSize];
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_real_distribution<float> dist(-1.0f, 1.0f);
    
    for (uint32_t i = 0; i < bufferSize; ++i) {
        sourceData[i] = dist(gen);
    }
    
    const int iterations = 10000;
    
    // Test SIMD mix with gain
    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < iterations; ++i) {
        testBuf->clear();
        testBuf->mixFrom(sourceData, bufferSize, 0.7f);
    }
    auto end = std::chrono::high_resolution_clock::now();
    
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
    double throughput = (double)(iterations * bufferSize * sizeof(float)) / (duration.count() / 1000.0);
    
    std::cout << "✓ SIMD mix operations:" << std::endl;
    std::cout << "  " << iterations << " iterations in " << duration.count() << "µs" << std::endl;
    std::cout << "  Throughput: " << (throughput / 1024.0 / 1024.0) << " MB/s" << std::endl;
    std::cout << "  Average per iteration: " << (duration.count() / (double)iterations) << "µs" << std::endl;
    
    pool.release(testBuf);
    
    std::cout << "\nBuffer pool statistics:" << std::endl;
    std::cout << "  Peak usage: " << pool.getPeakAllocated() << "/" << numBuffers << std::endl;
    std::cout << "✓ Buffer pool tests passed!" << std::endl;
}

void testLockFreeQueue() {
    std::cout << "\n=== Testing Lock-Free Queue ===" << std::endl;
    
    LockFreeQueue<int, 64> queue;
    
    // Test basic push/pop
    std::cout << "Testing basic operations..." << std::endl;
    assert(queue.empty());
    
    for (int i = 0; i < 10; ++i) {
        assert(queue.push(std::move(i)));
    }
    
    assert(!queue.empty());
    
    for (int i = 0; i < 10; ++i) {
        int value;
        assert(queue.pop(value));
        assert(value == i);
    }
    
    assert(queue.empty());
    std::cout << "✓ Basic push/pop operations work" << std::endl;
    
    // Test concurrent access
    std::cout << "Testing concurrent access..." << std::endl;
    std::atomic<int> producerSum{0};
    std::atomic<int> consumerSum{0};
    const int numItems = 1000;
    
    std::thread producer([&queue, &producerSum, numItems]() {
        for (int i = 0; i < numItems; ++i) {
            while (!queue.push(std::move(i))) {
                std::this_thread::yield();
            }
            producerSum.fetch_add(i);
        }
    });
    
    std::thread consumer([&queue, &consumerSum, numItems]() {
        for (int i = 0; i < numItems; ++i) {
            int value;
            while (!queue.pop(value)) {
                std::this_thread::yield();
            }
            consumerSum.fetch_add(value);
        }
    });
    
    producer.join();
    consumer.join();
    
    assert(producerSum.load() == consumerSum.load());
    std::cout << "✓ Concurrent access: producer sum = consumer sum = " << producerSum.load() << std::endl;
    
    std::cout << "✓ Lock-free queue tests passed!" << std::endl;
}

void benchmarkParallelProcessing() {
    std::cout << "\n=== Benchmarking Parallel Processing ===" << std::endl;
    
    CarlaEngineThreadPool pool(std::thread::hardware_concurrency(), 0);
    pool.start();
    
    const size_t dataSize = 1000000;
    std::vector<float> data(dataSize);
    
    // Initialize with random data
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_real_distribution<float> dist(-1.0f, 1.0f);
    for (auto& val : data) {
        val = dist(gen);
    }
    
    // Sequential processing
    auto seqStart = std::chrono::high_resolution_clock::now();
    volatile float seqSum = 0.0f;  // volatile prevents optimization
    for (size_t i = 0; i < dataSize; ++i) {
        float temp = std::sin(data[i]) * std::cos(data[i]);
        seqSum = seqSum + temp;  // Force actual computation
    }
    auto seqEnd = std::chrono::high_resolution_clock::now();
    auto seqDuration = std::chrono::duration_cast<std::chrono::microseconds>(seqEnd - seqStart);
    
    // Parallel processing with better strategy
    const size_t numThreads = pool.getNumWorkers();
    std::vector<float> partialSums(numThreads, 0.0f);
    
    auto parStart = std::chrono::high_resolution_clock::now();
    
    // Each thread accumulates to its own sum to avoid contention
    const size_t chunkSize = (dataSize + numThreads - 1) / numThreads;
    std::vector<std::future<void>> futures;
    
    for (size_t t = 0; t < numThreads; ++t) {
        size_t start = t * chunkSize;
        size_t end = std::min(start + chunkSize, dataSize);
        
        futures.push_back(pool.submitTask([&data, &partialSums, t, start, end]() {
            float localSum = 0.0f;
            for (size_t i = start; i < end; ++i) {
                localSum += std::sin(data[i]) * std::cos(data[i]);
            }
            partialSums[t] = localSum;
        }));
    }
    
    // Wait for all tasks
    for (auto& f : futures) {
        f.wait();
    }
    
    // Combine partial sums
    volatile float parSum = 0.0f;
    for (float partial : partialSums) {
        parSum = parSum + partial;
    }
    
    auto parEnd = std::chrono::high_resolution_clock::now();
    auto parDuration = std::chrono::duration_cast<std::chrono::microseconds>(parEnd - parStart);
    
    std::cout << "Processing " << dataSize << " samples:" << std::endl;
    std::cout << "  Sequential: " << seqDuration.count() << "µs" << std::endl;
    std::cout << "  Parallel:   " << parDuration.count() << "µs" << std::endl;
    float speedup = (seqDuration.count() > 0) ? 
                    (float)seqDuration.count() / parDuration.count() : 0.0f;
    std::cout << "  Speedup:    " << speedup << "x" << std::endl;
    std::cout << "  Cores used: " << pool.getNumWorkers() << std::endl;
    
    pool.stop();
}

int main() {
    std::cout << "=== Carla C++20 Parallel Processing Test ===" << std::endl;
    std::cout << "Hardware concurrency: " << std::thread::hardware_concurrency() << " cores" << std::endl;
    
    #ifdef __AVX__
    std::cout << "AVX support: YES" << std::endl;
    #elif defined(__SSE__)
    std::cout << "SSE support: YES" << std::endl;
    #else
    std::cout << "SIMD support: NO" << std::endl;
    #endif
    
    try {
        testLockFreeQueue();
        testThreadPool();
        testBufferPool();
        benchmarkParallelProcessing();
        
        std::cout << "\n✅ All tests passed successfully!" << std::endl;
        std::cout << "C++20 features working correctly!" << std::endl;
        return 0;
    }
    catch (const std::exception& e) {
        std::cerr << "\n❌ Test failed with exception: " << e.what() << std::endl;
        return 1;
    }
}