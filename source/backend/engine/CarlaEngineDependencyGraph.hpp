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

#ifndef CARLA_ENGINE_DEPENDENCY_GRAPH_HPP_INCLUDED
#define CARLA_ENGINE_DEPENDENCY_GRAPH_HPP_INCLUDED

#include "CarlaBackend.h"
#include "CarlaUtils.hpp"

#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <memory>
#include <atomic>

CARLA_BACKEND_START_NAMESPACE

// -----------------------------------------------------------------------
// Forward declarations

class CarlaEngineClient;
struct EnginePluginData;

// -----------------------------------------------------------------------
// Plugin dependency node

struct PluginNode {
    uint pluginId;
    CarlaEngineClient* client;
    
    // Plugins that must complete before this one can run
    std::vector<uint> dependencies;
    
    // Plugins that depend on this one
    std::vector<uint> dependents;
    
    // Execution layer (0 = can run immediately, 1 = depends on layer 0, etc.)
    uint executionLayer;
    
    // For cycle detection
    bool visited;
    bool inStack;
    
    // Performance metrics
    std::atomic<uint64_t> lastProcessTime;
    std::atomic<uint64_t> avgProcessTime;
    
    PluginNode(uint id, CarlaEngineClient* c) noexcept
        : pluginId(id)
        , client(c)
        , executionLayer(0)
        , visited(false)
        , inStack(false)
        , lastProcessTime(0)
        , avgProcessTime(0) {}
};

// -----------------------------------------------------------------------
// Audio connection information

struct AudioConnection {
    uint sourcePluginId;
    uint sourcePortIndex;
    uint targetPluginId;
    uint targetPortIndex;
    
    AudioConnection(uint srcPlugin, uint srcPort, uint tgtPlugin, uint tgtPort) noexcept
        : sourcePluginId(srcPlugin)
        , sourcePortIndex(srcPort)
        , targetPluginId(tgtPlugin)
        , targetPortIndex(tgtPort) {}
};

// -----------------------------------------------------------------------
// Execution layer for parallel processing

struct ExecutionLayer {
    std::vector<uint> pluginIds;
    uint layerIndex;
    
    // Can all plugins in this layer run in parallel?
    bool canRunParallel;
    
    ExecutionLayer(uint index) noexcept
        : layerIndex(index)
        , canRunParallel(true) {}
};

// -----------------------------------------------------------------------
// Dependency graph for parallel plugin processing

class CarlaEngineDependencyGraph {
public:
    CarlaEngineDependencyGraph() noexcept;
    ~CarlaEngineDependencyGraph();
    
    // Graph construction
    void clear() noexcept;
    void addPlugin(uint pluginId, CarlaEngineClient* client) noexcept;
    void removePlugin(uint pluginId) noexcept;
    void addConnection(uint sourcePluginId, uint sourcePort, 
                      uint targetPluginId, uint targetPort) noexcept;
    void removeConnection(uint sourcePluginId, uint sourcePort,
                         uint targetPluginId, uint targetPort) noexcept;
    
    // Graph analysis
    bool analyze() noexcept;
    bool hasCycles() const noexcept { return fHasCycles; }
    uint getNumLayers() const noexcept { return static_cast<uint>(fExecutionLayers.size()); }
    
    // Execution information
    const ExecutionLayer* getLayer(uint index) const noexcept;
    const std::vector<ExecutionLayer>& getLayers() const noexcept { return fExecutionLayers; }
    
    // Plugin information
    uint getPluginLayer(uint pluginId) const noexcept;
    const std::vector<uint>& getPluginDependencies(uint pluginId) const noexcept;
    const std::vector<uint>& getPluginDependents(uint pluginId) const noexcept;
    
    // Performance metrics
    void updatePluginProcessTime(uint pluginId, uint64_t microseconds) noexcept;
    uint64_t getPluginAvgProcessTime(uint pluginId) const noexcept;
    
    // Debug information
    void printGraph() const noexcept;
    void printExecutionOrder() const noexcept;
    
private:
    std::unordered_map<uint, std::unique_ptr<PluginNode>> fNodes;
    std::vector<AudioConnection> fConnections;
    std::vector<ExecutionLayer> fExecutionLayers;
    
    bool fHasCycles;
    bool fNeedsAnalysis;
    
    // Internal analysis methods
    bool detectCycles() noexcept;
    bool detectCyclesDFS(PluginNode* node, std::unordered_set<uint>& visited,
                        std::unordered_set<uint>& recStack) noexcept;
    void computeExecutionLayers() noexcept;
    void topologicalSort(std::vector<uint>& sortedIds) noexcept;
    void topologicalSortDFS(PluginNode* node, std::unordered_set<uint>& visited,
                           std::vector<uint>& sortedIds) noexcept;
    
    CARLA_DECLARE_NON_COPYABLE(CarlaEngineDependencyGraph)
};

CARLA_BACKEND_END_NAMESPACE

#endif // CARLA_ENGINE_DEPENDENCY_GRAPH_HPP_INCLUDED