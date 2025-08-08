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

#ifndef CARLA_ENGINE_BUFFER_POOL_HPP_INCLUDED
#define CARLA_ENGINE_BUFFER_POOL_HPP_INCLUDED

#include "CarlaBackend.h"
#include "CarlaUtils.hpp"

#include <atomic>
#include <memory>
#include <vector>
#include <stack>
#include <mutex>
#include <immintrin.h>  // For SIMD
#include <cstring>

CARLA_BACKEND_START_NAMESPACE

// -----------------------------------------------------------------------
// Aligned audio buffer for SIMD operations

class alignas(64) AudioBuffer {
public:
    AudioBuffer(uint32_t size) noexcept
        : fSize(size)
        , fData(nullptr)
    {
        // Allocate aligned memory for SIMD
        fData = static_cast<float*>(std::aligned_alloc(64, size * sizeof(float)));
        
        if (fData != nullptr)
            clear();
    }
    
    ~AudioBuffer()
    {
        if (fData != nullptr)
            std::free(fData);
    }
    
    void clear() noexcept
    {
        if (fData != nullptr)
            std::memset(fData, 0, fSize * sizeof(float));
    }
    
    void copyFrom(const float* source, uint32_t samples) noexcept
    {
        CARLA_SAFE_ASSERT_RETURN(source != nullptr,);
        CARLA_SAFE_ASSERT_RETURN(samples <= fSize,);
        
        std::memcpy(fData, source, samples * sizeof(float));
    }
    
    void copyTo(float* dest, uint32_t samples) const noexcept
    {
        CARLA_SAFE_ASSERT_RETURN(dest != nullptr,);
        CARLA_SAFE_ASSERT_RETURN(samples <= fSize,);
        
        std::memcpy(dest, fData, samples * sizeof(float));
    }
    
    // SIMD-optimized mix operation
    void mixFrom(const float* source, uint32_t samples, float gain = 1.0f) noexcept
    {
        CARLA_SAFE_ASSERT_RETURN(source != nullptr,);
        CARLA_SAFE_ASSERT_RETURN(samples <= fSize,);
        
        if (gain == 0.0f)
            return;
        
        if (gain == 1.0f)
        {
            // Simple addition
            uint32_t i = 0;
            
            // SIMD path for aligned data
            #ifdef __AVX__
            // Check alignment before using aligned loads
            if (reinterpret_cast<uintptr_t>(source) % 32 == 0 &&
                reinterpret_cast<uintptr_t>(fData) % 32 == 0)
            {
                for (; i + 8 <= samples; i += 8)
                {
                    __m256 src = _mm256_load_ps(&source[i]);
                    __m256 dst = _mm256_load_ps(&fData[i]);
                    dst = _mm256_add_ps(dst, src);
                    _mm256_store_ps(&fData[i], dst);
                }
            }
            else
            {
                // Use unaligned loads/stores
                for (; i + 8 <= samples; i += 8)
                {
                    __m256 src = _mm256_loadu_ps(&source[i]);
                    __m256 dst = _mm256_loadu_ps(&fData[i]);
                    dst = _mm256_add_ps(dst, src);
                    _mm256_storeu_ps(&fData[i], dst);
                }
            }
            #elif defined(__SSE__)
            for (; i + 4 <= samples; i += 4)
            {
                __m128 src = _mm_load_ps(&source[i]);
                __m128 dst = _mm_load_ps(&fData[i]);
                dst = _mm_add_ps(dst, src);
                _mm_store_ps(&fData[i], dst);
            }
            #endif
            
            // Scalar path for remaining samples
            for (; i < samples; ++i)
                fData[i] += source[i];
        }
        else
        {
            // Mix with gain
            uint32_t i = 0;
            
            #ifdef __AVX__
            const __m256 gainVec = _mm256_set1_ps(gain);
            // Check alignment before using aligned loads
            if (reinterpret_cast<uintptr_t>(source) % 32 == 0 &&
                reinterpret_cast<uintptr_t>(fData) % 32 == 0)
            {
                for (; i + 8 <= samples; i += 8)
                {
                    __m256 src = _mm256_load_ps(&source[i]);
                    __m256 dst = _mm256_load_ps(&fData[i]);
                    src = _mm256_mul_ps(src, gainVec);
                    dst = _mm256_add_ps(dst, src);
                    _mm256_store_ps(&fData[i], dst);
                }
            }
            else
            {
                // Use unaligned loads/stores
                for (; i + 8 <= samples; i += 8)
                {
                    __m256 src = _mm256_loadu_ps(&source[i]);
                    __m256 dst = _mm256_loadu_ps(&fData[i]);
                    src = _mm256_mul_ps(src, gainVec);
                    dst = _mm256_add_ps(dst, src);
                    _mm256_storeu_ps(&fData[i], dst);
                }
            }
            #elif defined(__SSE__)
            const __m128 gainVec = _mm_set1_ps(gain);
            for (; i + 4 <= samples; i += 4)
            {
                __m128 src = _mm_load_ps(&source[i]);
                __m128 dst = _mm_load_ps(&fData[i]);
                src = _mm_mul_ps(src, gainVec);
                dst = _mm_add_ps(dst, src);
                _mm_store_ps(&fData[i], dst);
            }
            #endif
            
            // Scalar path for remaining samples
            for (; i < samples; ++i)
                fData[i] += source[i] * gain;
        }
    }
    
    float* getData() noexcept { return fData; }
    const float* getData() const noexcept { return fData; }
    uint32_t getSize() const noexcept { return fSize; }
    
private:
    uint32_t fSize;
    float* fData;
    
    CARLA_DECLARE_NON_COPYABLE(AudioBuffer)
};

// -----------------------------------------------------------------------
// Lock-free buffer pool for real-time audio processing

class CarlaEngineBufferPool {
public:
    CarlaEngineBufferPool(uint32_t bufferSize, uint32_t numBuffers) noexcept
        : fBufferSize(bufferSize)
        , fNumBuffers(numBuffers)
        , fAllocatedCount(0)
    {
        // Pre-allocate all buffers
        fBuffers.reserve(numBuffers);
        for (uint32_t i = 0; i < numBuffers; ++i)
        {
            fBuffers.emplace_back(std::make_unique<AudioBuffer>(bufferSize));
        }
        
        // Initialize free list with all buffers
        for (uint32_t i = 0; i < numBuffers; ++i)
        {
            fFreeIndices.push(i);
        }
        
        carla_stdout("CarlaEngineBufferPool: Created %u buffers of size %u",
                    numBuffers, bufferSize);
    }
    
    ~CarlaEngineBufferPool()
    {
        carla_stdout("CarlaEngineBufferPool: Destroyed (peak usage: %u/%u buffers)",
                    fAllocatedCount.load(), fNumBuffers);
    }
    
    // Get a buffer from the pool (real-time safe)
    AudioBuffer* acquire() noexcept
    {
        std::lock_guard<std::mutex> lock(fMutex);
        
        if (fFreeIndices.empty())
        {
            carla_stderr2("CarlaEngineBufferPool: Out of buffers!");
            return nullptr;
        }
        
        uint32_t index = fFreeIndices.top();
        fFreeIndices.pop();
        
        AudioBuffer* buffer = fBuffers[index].get();
        buffer->clear();
        
        // Track peak usage
        uint32_t current = fAllocatedCount.fetch_add(1) + 1;
        uint32_t peak = fPeakAllocated.load();
        while (current > peak && !fPeakAllocated.compare_exchange_weak(peak, current))
            ;
        
        return buffer;
    }
    
    // Return a buffer to the pool (real-time safe)
    void release(AudioBuffer* buffer) noexcept
    {
        if (buffer == nullptr)
            return;
        
        std::lock_guard<std::mutex> lock(fMutex);
        
        // Find the buffer index
        for (uint32_t i = 0; i < fNumBuffers; ++i)
        {
            if (fBuffers[i].get() == buffer)
            {
                fFreeIndices.push(i);
                fAllocatedCount.fetch_sub(1);
                return;
            }
        }
        
        carla_stderr2("CarlaEngineBufferPool: Attempted to release unknown buffer!");
    }
    
    // RAII wrapper for automatic buffer management
    class ScopedBuffer {
    public:
        ScopedBuffer(CarlaEngineBufferPool& pool) noexcept
            : fPool(pool)
            , fBuffer(pool.acquire()) {}
        
        ~ScopedBuffer()
        {
            if (fBuffer != nullptr)
                fPool.release(fBuffer);
        }
        
        AudioBuffer* get() noexcept { return fBuffer; }
        const AudioBuffer* get() const noexcept { return fBuffer; }
        
        AudioBuffer* operator->() noexcept { return fBuffer; }
        const AudioBuffer* operator->() const noexcept { return fBuffer; }
        
        bool isValid() const noexcept { return fBuffer != nullptr; }
        
    private:
        CarlaEngineBufferPool& fPool;
        AudioBuffer* fBuffer;
        
        CARLA_DECLARE_NON_COPYABLE(ScopedBuffer)
    };
    
    uint32_t getBufferSize() const noexcept { return fBufferSize; }
    uint32_t getNumBuffers() const noexcept { return fNumBuffers; }
    uint32_t getAllocatedCount() const noexcept { return fAllocatedCount.load(); }
    uint32_t getPeakAllocated() const noexcept { return fPeakAllocated.load(); }
    
    void resetStatistics() noexcept
    {
        fPeakAllocated.store(fAllocatedCount.load());
    }
    
private:
    const uint32_t fBufferSize;
    const uint32_t fNumBuffers;
    
    std::vector<std::unique_ptr<AudioBuffer>> fBuffers;
    std::stack<uint32_t> fFreeIndices;
    std::mutex fMutex;
    
    std::atomic<uint32_t> fAllocatedCount;
    std::atomic<uint32_t> fPeakAllocated{0};
    
    CARLA_DECLARE_NON_COPYABLE(CarlaEngineBufferPool)
};

// -----------------------------------------------------------------------
// Multi-channel buffer for plugin processing

class MultiChannelBuffer {
public:
    MultiChannelBuffer(uint32_t channels, uint32_t samples) noexcept
        : fChannels(channels)
        , fSamples(samples)
    {
        fBuffers.reserve(channels);
        for (uint32_t i = 0; i < channels; ++i)
        {
            fBuffers.emplace_back(std::make_unique<AudioBuffer>(samples));
        }
    }
    
    void clear() noexcept
    {
        for (auto& buffer : fBuffers)
            buffer->clear();
    }
    
    AudioBuffer* getChannel(uint32_t channel) noexcept
    {
        CARLA_SAFE_ASSERT_RETURN(channel < fChannels, nullptr);
        return fBuffers[channel].get();
    }
    
    const AudioBuffer* getChannel(uint32_t channel) const noexcept
    {
        CARLA_SAFE_ASSERT_RETURN(channel < fChannels, nullptr);
        return fBuffers[channel].get();
    }
    
    float** getRawBuffers() noexcept
    {
        if (fRawBuffers.empty())
        {
            fRawBuffers.resize(fChannels);
            for (uint32_t i = 0; i < fChannels; ++i)
                fRawBuffers[i] = fBuffers[i]->getData();
        }
        return fRawBuffers.data();
    }
    
    uint32_t getChannelCount() const noexcept { return fChannels; }
    uint32_t getSampleCount() const noexcept { return fSamples; }
    
private:
    const uint32_t fChannels;
    const uint32_t fSamples;
    
    std::vector<std::unique_ptr<AudioBuffer>> fBuffers;
    mutable std::vector<float*> fRawBuffers;
    
    CARLA_DECLARE_NON_COPYABLE(MultiChannelBuffer)
};

CARLA_BACKEND_END_NAMESPACE

#endif // CARLA_ENGINE_BUFFER_POOL_HPP_INCLUDED