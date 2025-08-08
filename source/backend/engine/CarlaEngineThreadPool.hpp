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

#ifndef CARLA_ENGINE_THREAD_POOL_HPP_INCLUDED
#define CARLA_ENGINE_THREAD_POOL_HPP_INCLUDED

#include "CarlaBackend.h"
#include "CarlaUtils.hpp"

#include <atomic>
#include <condition_variable>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <queue>
#include <thread>
#include <vector>
#include <semaphore>
#include <latch>
#include <barrier>

CARLA_BACKEND_START_NAMESPACE

// -----------------------------------------------------------------------
// Lock-free queue for real-time safe task submission

template<typename T, size_t Size = 1024>
class LockFreeQueue {
public:
    LockFreeQueue() noexcept
        : fHead(0)
        , fTail(0) {}
    
    bool push(T&& item) noexcept
    {
        const size_t currentTail = fTail.load(std::memory_order_relaxed);
        const size_t nextTail = (currentTail + 1) % Size;
        
        if (nextTail == fHead.load(std::memory_order_acquire))
            return false; // Queue is full
        
        fData[currentTail] = std::move(item);
        fTail.store(nextTail, std::memory_order_release);
        return true;
    }
    
    bool pop(T& item) noexcept
    {
        const size_t currentHead = fHead.load(std::memory_order_relaxed);
        
        if (currentHead == fTail.load(std::memory_order_acquire))
            return false; // Queue is empty
        
        item = std::move(fData[currentHead]);
        fHead.store((currentHead + 1) % Size, std::memory_order_release);
        return true;
    }
    
    bool empty() const noexcept
    {
        return fHead.load(std::memory_order_acquire) == 
               fTail.load(std::memory_order_acquire);
    }
    
private:
    alignas(64) std::atomic<size_t> fHead;
    alignas(64) std::atomic<size_t> fTail;
    std::array<T, Size> fData;
};

// -----------------------------------------------------------------------
// Task type for the thread pool

using Task = std::function<void()>;

// -----------------------------------------------------------------------
// Worker thread for the pool

class WorkerThread {
public:
    WorkerThread(uint id, bool realtime = false) noexcept
        : fId(id)
        , fRealtime(realtime)
        , fRunning(false)
        , fThread(nullptr) {}
    
    ~WorkerThread()
    {
        stop();
    }
    
    void start()
    {
        if (fRunning.load())
            return;
        
        fRunning.store(true);
        fThread = std::make_unique<std::thread>(&WorkerThread::run, this);
        
        if (fRealtime)
        {
            // Set real-time priority
            struct sched_param param;
            param.sched_priority = 80;
            pthread_setschedparam(fThread->native_handle(), SCHED_FIFO, &param);
        }
        
        // Set CPU affinity if possible
        #ifdef __linux__
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        CPU_SET(fId % std::thread::hardware_concurrency(), &cpuset);
        pthread_setaffinity_np(fThread->native_handle(), sizeof(cpu_set_t), &cpuset);
        #endif
    }
    
    void stop()
    {
        if (!fRunning.load())
            return;
        
        fRunning.store(false);
        fCondition.notify_all();
        
        if (fThread && fThread->joinable())
            fThread->join();
        
        fThread.reset();
    }
    
    void submitTask(Task&& task)
    {
        {
            std::unique_lock<std::mutex> lock(fMutex);
            fTasks.push(std::move(task));
        }
        fCondition.notify_one();
    }
    
    bool submitTaskRealtime(Task&& task)
    {
        if (fRealtimeTasks.push(std::move(task)))
        {
            fCondition.notify_one();
            return true;
        }
        return false;
    }
    
    uint getId() const noexcept { return fId; }
    bool isRealtime() const noexcept { return fRealtime; }
    
private:
    void run()
    {
        carla_debug("WorkerThread %u started (realtime=%s)", fId, fRealtime ? "yes" : "no");
        
        while (fRunning.load())
        {
            Task task;
            
            // Check real-time queue first (lock-free)
            if (fRealtimeTasks.pop(task))
            {
                task();
                continue;
            }
            
            // Check normal queue (with lock)
            {
                std::unique_lock<std::mutex> lock(fMutex);
                fCondition.wait(lock, [this] {
                    return !fTasks.empty() || !fRunning.load();
                });
                
                if (!fRunning.load())
                    break;
                
                if (!fTasks.empty())
                {
                    task = std::move(fTasks.front());
                    fTasks.pop();
                }
            }
            
            if (task)
                task();
        }
        
        carla_debug("WorkerThread %u stopped", fId);
    }
    
    uint fId;
    bool fRealtime;
    std::atomic<bool> fRunning;
    std::unique_ptr<std::thread> fThread;
    
    std::mutex fMutex;
    std::condition_variable fCondition;
    std::queue<Task> fTasks;
    LockFreeQueue<Task> fRealtimeTasks;
    
    CARLA_DECLARE_NON_COPYABLE(WorkerThread)
};

// -----------------------------------------------------------------------
// Modern C++20 thread pool with real-time support

class CarlaEngineThreadPool {
public:
    CarlaEngineThreadPool(uint numWorkers = 0, uint numRealtimeWorkers = 0) noexcept
        : fNumWorkers(numWorkers > 0 ? numWorkers : std::thread::hardware_concurrency())
        , fNumRealtimeWorkers(numRealtimeWorkers)
        , fNextWorker(0)
        , fNextRealtimeWorker(0)
    {
        // Create normal workers
        for (uint i = 0; i < fNumWorkers; ++i)
        {
            fWorkers.emplace_back(std::make_unique<WorkerThread>(i, false));
        }
        
        // Create real-time workers
        for (uint i = 0; i < fNumRealtimeWorkers; ++i)
        {
            fRealtimeWorkers.emplace_back(
                std::make_unique<WorkerThread>(fNumWorkers + i, true));
        }
        
        carla_stdout("CarlaEngineThreadPool created with %u workers and %u realtime workers",
                    fNumWorkers, fNumRealtimeWorkers);
    }
    
    ~CarlaEngineThreadPool()
    {
        stop();
    }
    
    void start()
    {
        for (auto& worker : fWorkers)
            worker->start();
        
        for (auto& worker : fRealtimeWorkers)
            worker->start();
    }
    
    void stop()
    {
        for (auto& worker : fWorkers)
            worker->stop();
        
        for (auto& worker : fRealtimeWorkers)
            worker->stop();
    }
    
    // Submit task to normal worker pool
    template<typename F>
    auto submitTask(F&& func) -> std::future<decltype(func())>
    {
        using ReturnType = decltype(func());
        
        auto task = std::make_shared<std::packaged_task<ReturnType()>>(
            std::forward<F>(func));
        
        auto future = task->get_future();
        
        uint workerId = fNextWorker.fetch_add(1) % fNumWorkers;
        fWorkers[workerId]->submitTask([task]() { (*task)(); });
        
        return future;
    }
    
    // Submit task to real-time worker pool (returns false if queue is full)
    template<typename F>
    bool submitRealtimeTask(F&& func)
    {
        if (fNumRealtimeWorkers == 0)
            return false;
        
        uint workerId = fNextRealtimeWorker.fetch_add(1) % fNumRealtimeWorkers;
        return fRealtimeWorkers[workerId]->submitTaskRealtime(
            std::forward<F>(func));
    }
    
    // Execute tasks in parallel and wait for completion
    template<typename F>
    void parallelFor(size_t start, size_t end, F&& func)
    {
        const size_t numTasks = end - start;
        const size_t tasksPerWorker = (numTasks + fNumWorkers - 1) / fNumWorkers;
        
        std::vector<std::future<void>> futures;
        futures.reserve(fNumWorkers);
        
        for (size_t i = 0; i < fNumWorkers && start < end; ++i)
        {
            size_t taskStart = start;
            size_t taskEnd = std::min(start + tasksPerWorker, end);
            
            futures.push_back(submitTask([taskStart, taskEnd, func]() {
                for (size_t j = taskStart; j < taskEnd; ++j)
                {
                    func(j);
                }
            }));
            
            start = taskEnd;
        }
        
        // Wait for all tasks to complete
        for (auto& future : futures)
        {
            future.wait();
        }
    }
    
    // Execute a group of tasks in parallel using C++20 latch
    void executeParallelGroup(const std::vector<Task>& tasks)
    {
        if (tasks.empty())
            return;
        
        std::latch taskLatch(tasks.size());
        
        for (const auto& task : tasks)
        {
            submitTask([task, &taskLatch]() {
                task();
                taskLatch.count_down();
            });
        }
        
        taskLatch.wait();
    }
    
    // Execute tasks with barrier synchronization (C++20)
    // Note: Simplified version without custom completion function due to std::barrier limitations
    void executeWithBarrier(const std::vector<Task>& tasks, 
                           std::function<void()> onCompletion = nullptr)
    {
        if (tasks.empty())
            return;
        
        // Use latch for synchronization instead of barrier for simplicity
        auto latchPtr = std::make_shared<std::latch>(tasks.size());
        auto completionFlag = std::make_shared<std::atomic<bool>>(false);
        
        std::vector<std::future<void>> futures;
        futures.reserve(tasks.size());
        
        for (const auto& task : tasks)
        {
            futures.push_back(submitTask([task, latchPtr, completionFlag, onCompletion]() {
                task();
                latchPtr->count_down();
                
                // Check if we're the last one
                if (latchPtr->try_wait())
                {
                    bool expected = false;
                    if (completionFlag->compare_exchange_strong(expected, true))
                    {
                        if (onCompletion)
                            onCompletion();
                    }
                }
            }));
        }
        
        // Wait for all tasks to complete
        for (auto& future : futures)
        {
            future.wait();
        }
    }
    
    uint getNumWorkers() const noexcept { return fNumWorkers; }
    uint getNumRealtimeWorkers() const noexcept { return fNumRealtimeWorkers; }
    
private:
    const uint fNumWorkers;
    const uint fNumRealtimeWorkers;
    
    std::vector<std::unique_ptr<WorkerThread>> fWorkers;
    std::vector<std::unique_ptr<WorkerThread>> fRealtimeWorkers;
    
    std::atomic<uint> fNextWorker;
    std::atomic<uint> fNextRealtimeWorker;
    
    CARLA_DECLARE_NON_COPYABLE(CarlaEngineThreadPool)
};

CARLA_BACKEND_END_NAMESPACE

#endif // CARLA_ENGINE_THREAD_POOL_HPP_INCLUDED