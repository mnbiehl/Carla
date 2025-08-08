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

#include "CarlaEngineDependencyGraph.hpp"
#include "CarlaEngineInternal.hpp"
#include "CarlaEngineClient.hpp"

#include <algorithm>
#include <queue>
#include <chrono>

CARLA_BACKEND_START_NAMESPACE

// -----------------------------------------------------------------------
// CarlaEngineDependencyGraph

CarlaEngineDependencyGraph::CarlaEngineDependencyGraph() noexcept
    : fHasCycles(false)
    , fNeedsAnalysis(true)
{
}

CarlaEngineDependencyGraph::~CarlaEngineDependencyGraph()
{
    clear();
}

void CarlaEngineDependencyGraph::clear() noexcept
{
    fNodes.clear();
    fConnections.clear();
    fExecutionLayers.clear();
    fHasCycles = false;
    fNeedsAnalysis = true;
}

void CarlaEngineDependencyGraph::addPlugin(uint pluginId, CarlaEngineClient* client) noexcept
{
    CARLA_SAFE_ASSERT_RETURN(client != nullptr,);
    
    fNodes[pluginId] = std::make_unique<PluginNode>(pluginId, client);
    fNeedsAnalysis = true;
    
    carla_debug("CarlaEngineDependencyGraph::addPlugin(%u)", pluginId);
}

void CarlaEngineDependencyGraph::removePlugin(uint pluginId) noexcept
{
    auto it = fNodes.find(pluginId);
    if (it == fNodes.end())
        return;
    
    // Remove all connections involving this plugin
    fConnections.erase(
        std::remove_if(fConnections.begin(), fConnections.end(),
            [pluginId](const AudioConnection& conn) {
                return conn.sourcePluginId == pluginId || conn.targetPluginId == pluginId;
            }),
        fConnections.end()
    );
    
    // Remove from other plugins' dependency lists
    for (auto& [id, node] : fNodes)
    {
        if (id == pluginId)
            continue;
            
        node->dependencies.erase(
            std::remove(node->dependencies.begin(), node->dependencies.end(), pluginId),
            node->dependencies.end()
        );
        
        node->dependents.erase(
            std::remove(node->dependents.begin(), node->dependents.end(), pluginId),
            node->dependents.end()
        );
    }
    
    fNodes.erase(it);
    fNeedsAnalysis = true;
    
    carla_debug("CarlaEngineDependencyGraph::removePlugin(%u)", pluginId);
}

void CarlaEngineDependencyGraph::addConnection(uint sourcePluginId, uint sourcePort,
                                              uint targetPluginId, uint targetPort) noexcept
{
    // Check if both plugins exist
    if (fNodes.find(sourcePluginId) == fNodes.end() || 
        fNodes.find(targetPluginId) == fNodes.end())
    {
        carla_stderr2("CarlaEngineDependencyGraph::addConnection() - Invalid plugin IDs");
        return;
    }
    
    // Check if connection already exists
    for (const auto& conn : fConnections)
    {
        if (conn.sourcePluginId == sourcePluginId && conn.sourcePortIndex == sourcePort &&
            conn.targetPluginId == targetPluginId && conn.targetPortIndex == targetPort)
        {
            return; // Connection already exists
        }
    }
    
    fConnections.emplace_back(sourcePluginId, sourcePort, targetPluginId, targetPort);
    
    // Update dependency information
    auto& sourceNode = fNodes[sourcePluginId];
    auto& targetNode = fNodes[targetPluginId];
    
    // Target depends on source
    if (std::find(targetNode->dependencies.begin(), targetNode->dependencies.end(), sourcePluginId) 
        == targetNode->dependencies.end())
    {
        targetNode->dependencies.push_back(sourcePluginId);
    }
    
    // Source has target as dependent
    if (std::find(sourceNode->dependents.begin(), sourceNode->dependents.end(), targetPluginId)
        == sourceNode->dependents.end())
    {
        sourceNode->dependents.push_back(targetPluginId);
    }
    
    fNeedsAnalysis = true;
    
    carla_debug("CarlaEngineDependencyGraph::addConnection(%u:%u -> %u:%u)",
                sourcePluginId, sourcePort, targetPluginId, targetPort);
}

void CarlaEngineDependencyGraph::removeConnection(uint sourcePluginId, uint sourcePort,
                                                 uint targetPluginId, uint targetPort) noexcept
{
    auto it = std::remove_if(fConnections.begin(), fConnections.end(),
        [=](const AudioConnection& conn) {
            return conn.sourcePluginId == sourcePluginId && conn.sourcePortIndex == sourcePort &&
                   conn.targetPluginId == targetPluginId && conn.targetPortIndex == targetPort;
        });
    
    if (it != fConnections.end())
    {
        fConnections.erase(it, fConnections.end());
        
        // Check if there are any remaining connections between these plugins
        bool hasOtherConnections = false;
        for (const auto& conn : fConnections)
        {
            if (conn.sourcePluginId == sourcePluginId && conn.targetPluginId == targetPluginId)
            {
                hasOtherConnections = true;
                break;
            }
        }
        
        // If no other connections, remove dependency
        if (!hasOtherConnections)
        {
            auto sourceIt = fNodes.find(sourcePluginId);
            auto targetIt = fNodes.find(targetPluginId);
            
            if (sourceIt != fNodes.end() && targetIt != fNodes.end())
            {
                auto& sourceNode = sourceIt->second;
                auto& targetNode = targetIt->second;
                
                targetNode->dependencies.erase(
                    std::remove(targetNode->dependencies.begin(), targetNode->dependencies.end(), sourcePluginId),
                    targetNode->dependencies.end()
                );
                
                sourceNode->dependents.erase(
                    std::remove(sourceNode->dependents.begin(), sourceNode->dependents.end(), targetPluginId),
                    sourceNode->dependents.end()
                );
            }
        }
        
        fNeedsAnalysis = true;
        
        carla_debug("CarlaEngineDependencyGraph::removeConnection(%u:%u -> %u:%u)",
                    sourcePluginId, sourcePort, targetPluginId, targetPort);
    }
}

bool CarlaEngineDependencyGraph::analyze() noexcept
{
    if (!fNeedsAnalysis)
        return !fHasCycles;
    
    carla_debug("CarlaEngineDependencyGraph::analyze() - Starting analysis");
    
    // Reset analysis state
    fExecutionLayers.clear();
    fHasCycles = false;
    
    for (auto& [id, node] : fNodes)
    {
        node->visited = false;
        node->inStack = false;
        node->executionLayer = 0;
    }
    
    // Step 1: Detect cycles
    fHasCycles = detectCycles();
    if (fHasCycles)
    {
        carla_stderr2("CarlaEngineDependencyGraph::analyze() - Cycle detected in plugin graph!");
        // We can still compute layers, but some plugins might have feedback loops
    }
    
    // Step 2: Compute execution layers
    computeExecutionLayers();
    
    fNeedsAnalysis = false;
    
    carla_debug("CarlaEngineDependencyGraph::analyze() - Complete. Layers: %u, Has cycles: %s",
                getNumLayers(), fHasCycles ? "yes" : "no");
    
    return !fHasCycles;
}

bool CarlaEngineDependencyGraph::detectCycles() noexcept
{
    std::unordered_set<uint> visited;
    std::unordered_set<uint> recStack;
    
    for (const auto& [id, node] : fNodes)
    {
        if (visited.find(id) == visited.end())
        {
            if (detectCyclesDFS(node.get(), visited, recStack))
                return true;
        }
    }
    
    return false;
}

bool CarlaEngineDependencyGraph::detectCyclesDFS(PluginNode* node,
                                                std::unordered_set<uint>& visited,
                                                std::unordered_set<uint>& recStack) noexcept
{
    visited.insert(node->pluginId);
    recStack.insert(node->pluginId);
    
    for (uint dependentId : node->dependents)
    {
        auto it = fNodes.find(dependentId);
        if (it == fNodes.end())
            continue;
        
        if (visited.find(dependentId) == visited.end())
        {
            if (detectCyclesDFS(it->second.get(), visited, recStack))
                return true;
        }
        else if (recStack.find(dependentId) != recStack.end())
        {
            // Found a cycle
            carla_stderr2("Cycle detected: Plugin %u -> Plugin %u", node->pluginId, dependentId);
            return true;
        }
    }
    
    recStack.erase(node->pluginId);
    return false;
}

void CarlaEngineDependencyGraph::computeExecutionLayers() noexcept
{
    if (fNodes.empty())
        return;
    
    // Use Kahn's algorithm for topological sorting with layer computation
    std::unordered_map<uint, uint> inDegree;
    std::queue<uint> queue;
    
    // Calculate in-degree for each node
    for (const auto& [id, node] : fNodes)
    {
        inDegree[id] = static_cast<uint>(node->dependencies.size());
        if (inDegree[id] == 0)
        {
            queue.push(id);
            node->executionLayer = 0;
        }
    }
    
    uint currentLayer = 0;
    
    while (!queue.empty())
    {
        size_t layerSize = queue.size();
        ExecutionLayer layer(currentLayer);
        
        for (size_t i = 0; i < layerSize; ++i)
        {
            uint pluginId = queue.front();
            queue.pop();
            
            layer.pluginIds.push_back(pluginId);
            
            auto it = fNodes.find(pluginId);
            if (it == fNodes.end())
                continue;
            
            // Process dependents
            for (uint dependentId : it->second->dependents)
            {
                inDegree[dependentId]--;
                if (inDegree[dependentId] == 0)
                {
                    queue.push(dependentId);
                    auto depIt = fNodes.find(dependentId);
                    if (depIt != fNodes.end())
                    {
                        depIt->second->executionLayer = currentLayer + 1;
                    }
                }
            }
        }
        
        if (!layer.pluginIds.empty())
        {
            fExecutionLayers.push_back(std::move(layer));
            currentLayer++;
        }
    }
    
    // Handle any remaining nodes (in case of cycles)
    for (const auto& [id, node] : fNodes)
    {
        bool found = false;
        for (const auto& layer : fExecutionLayers)
        {
            if (std::find(layer.pluginIds.begin(), layer.pluginIds.end(), id) != layer.pluginIds.end())
            {
                found = true;
                break;
            }
        }
        
        if (!found)
        {
            // Plugin is part of a cycle or disconnected
            if (fExecutionLayers.empty())
            {
                fExecutionLayers.emplace_back(0);
            }
            fExecutionLayers.back().pluginIds.push_back(id);
            fExecutionLayers.back().canRunParallel = false; // Cycles can't run in parallel
        }
    }
}

const ExecutionLayer* CarlaEngineDependencyGraph::getLayer(uint index) const noexcept
{
    if (index >= fExecutionLayers.size())
        return nullptr;
    
    return &fExecutionLayers[index];
}

uint CarlaEngineDependencyGraph::getPluginLayer(uint pluginId) const noexcept
{
    auto it = fNodes.find(pluginId);
    if (it == fNodes.end())
        return 0;
    
    return it->second->executionLayer;
}

const std::vector<uint>& CarlaEngineDependencyGraph::getPluginDependencies(uint pluginId) const noexcept
{
    static const std::vector<uint> empty;
    
    auto it = fNodes.find(pluginId);
    if (it == fNodes.end())
        return empty;
    
    return it->second->dependencies;
}

const std::vector<uint>& CarlaEngineDependencyGraph::getPluginDependents(uint pluginId) const noexcept
{
    static const std::vector<uint> empty;
    
    auto it = fNodes.find(pluginId);
    if (it == fNodes.end())
        return empty;
    
    return it->second->dependents;
}

void CarlaEngineDependencyGraph::updatePluginProcessTime(uint pluginId, uint64_t microseconds) noexcept
{
    auto it = fNodes.find(pluginId);
    if (it == fNodes.end())
        return;
    
    auto& node = it->second;
    uint64_t oldAvg = node->avgProcessTime.load();
    
    // Simple moving average with weight of 0.1 for new value
    uint64_t newAvg = (oldAvg * 9 + microseconds) / 10;
    
    node->lastProcessTime.store(microseconds);
    node->avgProcessTime.store(newAvg);
}

uint64_t CarlaEngineDependencyGraph::getPluginAvgProcessTime(uint pluginId) const noexcept
{
    auto it = fNodes.find(pluginId);
    if (it == fNodes.end())
        return 0;
    
    return it->second->avgProcessTime.load();
}

void CarlaEngineDependencyGraph::printGraph() const noexcept
{
    carla_stdout("=== Dependency Graph ===");
    carla_stdout("Plugins: %zu", fNodes.size());
    carla_stdout("Connections: %zu", fConnections.size());
    carla_stdout("Has Cycles: %s", fHasCycles ? "yes" : "no");
    
    for (const auto& [id, node] : fNodes)
    {
        carla_stdout("Plugin %u:", id);
        carla_stdout("  Layer: %u", node->executionLayer);
        carla_stdout("  Dependencies: %zu", node->dependencies.size());
        for (uint dep : node->dependencies)
        {
            carla_stdout("    <- Plugin %u", dep);
        }
        carla_stdout("  Dependents: %zu", node->dependents.size());
        for (uint dep : node->dependents)
        {
            carla_stdout("    -> Plugin %u", dep);
        }
    }
}

void CarlaEngineDependencyGraph::printExecutionOrder() const noexcept
{
    carla_stdout("=== Execution Order ===");
    carla_stdout("Total Layers: %u", getNumLayers());
    
    for (const auto& layer : fExecutionLayers)
    {
        carla_stdout("Layer %u (parallel=%s):", 
                    layer.layerIndex, 
                    layer.canRunParallel ? "yes" : "no");
        
        for (uint pluginId : layer.pluginIds)
        {
            auto it = fNodes.find(pluginId);
            if (it != fNodes.end())
            {
                uint64_t avgTime = it->second->avgProcessTime.load();
                carla_stdout("  Plugin %u (avg: %lu µs)", pluginId, avgTime);
            }
        }
    }
}

CARLA_BACKEND_END_NAMESPACE