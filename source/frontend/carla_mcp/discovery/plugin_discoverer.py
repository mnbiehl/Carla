"""
Main plugin discoverer for Carla MCP Server

Orchestrates the discovery process across multiple plugin directories and formats.
"""

import os
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .carla_discovery_parser import CarlaDiscoveryParser, PluginInfo
from .plugin_database import PluginDatabase

logger = logging.getLogger(__name__)


class PluginDiscoverer:
    """Main plugin discovery orchestrator"""
    
    # Standard plugin directory paths
    PLUGIN_DIRECTORIES = {
        'lv2': [
            '/usr/lib/lv2',
            '/usr/local/lib/lv2',
            '/usr/lib/x86_64-linux-gnu/lv2',
            '~/.lv2'
        ],
        'ladspa': [
            '/usr/lib/ladspa',
            '/usr/local/lib/ladspa',
            '/usr/lib/x86_64-linux-gnu/ladspa',
            '~/.ladspa'
        ],
        'vst2': [
            '/usr/lib/vst',
            '/usr/local/lib/vst',
            '/usr/lib/x86_64-linux-gnu/vst',
            '~/.vst'
        ],
        'vst3': [
            '/usr/lib/vst3',
            '/usr/local/lib/vst3',
            '~/.vst3'
        ]
    }
    
    def __init__(self, cache_file: Optional[str] = None, max_workers: int = 4):
        """
        Initialize plugin discoverer
        
        Args:
            cache_file: Path to cache file for persistent storage
            max_workers: Maximum number of worker threads for parallel discovery
        """
        self.parser = CarlaDiscoveryParser()
        self.database = PluginDatabase(cache_file)
        self.max_workers = max_workers
        self.logger = logging.getLogger(__name__)
        
        # Check if discovery tool is available
        if not self.parser.is_discovery_tool_available():
            self.logger.error("Carla discovery tool not available!")
            raise RuntimeError("Carla discovery tool not available at /usr/lib/carla/carla-discovery-native")
    
    def discover_all_plugins(self, force_refresh: bool = False) -> Dict[str, int]:
        """
        Discover all plugins in standard directories
        
        Args:
            force_refresh: Force rediscovery even if cache is valid
            
        Returns:
            Dictionary with plugin counts by type
        """
        # Check if we should use cache
        if not force_refresh and self.database.is_cache_valid():
            self.logger.info("Using cached plugin database")
            return self._get_discovery_summary()
        
        self.logger.info("Starting full plugin discovery...")
        start_time = time.time()
        
        # Clear existing database
        self.database.clear()
        
        # Discover plugins by type
        results = {}
        for plugin_type in self.PLUGIN_DIRECTORIES.keys():
            count = self._discover_plugins_by_type(plugin_type)
            results[plugin_type] = count
            self.logger.info(f"Discovered {count} {plugin_type.upper()} plugins")
        
        # Save to cache
        self.database.save_cache()
        
        total_time = time.time() - start_time
        total_plugins = sum(results.values())
        
        self.logger.info(f"Discovery complete: {total_plugins} plugins in {total_time:.2f}s")
        
        return results
    
    def _discover_plugins_by_type(self, plugin_type: str) -> int:
        """
        Discover plugins of a specific type
        
        Args:
            plugin_type: Type of plugins to discover
            
        Returns:
            Number of plugins discovered
        """
        directories = self.PLUGIN_DIRECTORIES.get(plugin_type, [])
        plugin_paths = []
        
        # Find all plugin files/directories
        for directory in directories:
            expanded_dir = os.path.expanduser(directory)
            if os.path.exists(expanded_dir):
                paths = self._find_plugin_paths(expanded_dir, plugin_type)
                plugin_paths.extend(paths)
        
        if not plugin_paths:
            self.logger.debug(f"No {plugin_type} plugins found")
            return 0
        
        self.logger.info(f"Discovering {len(plugin_paths)} {plugin_type.upper()} plugins...")
        
        # Discover plugins in parallel (each path may yield multiple plugins)
        discovered_count = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit discovery tasks - use discover_plugins (plural)
            future_to_path = {
                executor.submit(self.parser.discover_plugins, plugin_type, path): path
                for path in plugin_paths
            }

            # Process results - each future returns a list of PluginInfo
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    plugin_infos = future.result()
                    for plugin_info in plugin_infos:
                        self.database.add_plugin(plugin_info)
                        discovered_count += 1
                except Exception as e:
                    self.logger.debug(f"Discovery failed for {path}: {e}")
        
        return discovered_count
    
    def _find_plugin_paths(self, directory: str, plugin_type: str) -> List[str]:
        """
        Find plugin files/directories in a directory
        
        Args:
            directory: Directory to search
            plugin_type: Type of plugins to find
            
        Returns:
            List of plugin paths
        """
        paths = []
        
        try:
            if plugin_type == 'lv2':
                # LV2 plugins are directories ending in .lv2
                for item in os.listdir(directory):
                    if item.endswith('.lv2'):
                        path = os.path.join(directory, item)
                        if os.path.isdir(path):
                            paths.append(path)
            
            elif plugin_type == 'ladspa':
                # LADSPA plugins are .so files
                for item in os.listdir(directory):
                    if item.endswith('.so'):
                        path = os.path.join(directory, item)
                        if os.path.isfile(path):
                            paths.append(path)
            
            elif plugin_type == 'vst2':
                # VST2 plugins are .so files
                for item in os.listdir(directory):
                    if item.endswith('.so'):
                        path = os.path.join(directory, item)
                        if os.path.isfile(path):
                            paths.append(path)
            
            elif plugin_type == 'vst3':
                # VST3 plugins are .vst3 directories
                for item in os.listdir(directory):
                    if item.endswith('.vst3'):
                        path = os.path.join(directory, item)
                        if os.path.isdir(path):
                            paths.append(path)
        
        except PermissionError:
            self.logger.warning(f"Permission denied accessing {directory}")
        except Exception as e:
            self.logger.error(f"Error scanning {directory}: {e}")
        
        return paths
    
    def discover_plugin(self, plugin_path: str, plugin_type: Optional[str] = None) -> Optional[PluginInfo]:
        """
        Discover a single plugin
        
        Args:
            plugin_path: Path to plugin file or directory
            plugin_type: Plugin type (auto-detected if not provided)
            
        Returns:
            PluginInfo object or None if discovery failed
        """
        if plugin_type is None:
            plugin_type = self._detect_plugin_type(plugin_path)
            if plugin_type is None:
                self.logger.warning(f"Could not detect plugin type for {plugin_path}")
                return None
        
        return self.parser.discover_plugin(plugin_type, plugin_path)
    
    def _detect_plugin_type(self, plugin_path: str) -> Optional[str]:
        """
        Auto-detect plugin type from path
        
        Args:
            plugin_path: Path to plugin
            
        Returns:
            Plugin type or None if could not be detected
        """
        if plugin_path.endswith('.lv2') or plugin_path.endswith('.lv2/'):
            return 'lv2'
        elif plugin_path.endswith('.vst3') or plugin_path.endswith('.vst3/'):
            return 'vst3'
        elif plugin_path.endswith('.so'):
            # Check parent directory for clues
            parent_dir = os.path.dirname(plugin_path)
            if 'ladspa' in parent_dir.lower():
                return 'ladspa'
            elif 'vst' in parent_dir.lower():
                return 'vst2'
            else:
                # Default to LADSPA for .so files
                return 'ladspa'
        
        return None
    
    def get_database(self) -> PluginDatabase:
        """Get the plugin database"""
        return self.database
    
    def refresh_cache(self) -> bool:
        """
        Refresh the plugin cache
        
        Returns:
            True if cache was refreshed successfully
        """
        try:
            self.discover_all_plugins(force_refresh=True)
            return True
        except Exception as e:
            self.logger.error(f"Error refreshing cache: {e}")
            return False
    
    def _get_discovery_summary(self) -> Dict[str, int]:
        """Get summary of discovered plugins by type"""
        stats = self.database.get_statistics()
        return stats.get('by_type', {})
    
    def get_discovery_status(self) -> Dict[str, any]:
        """Get current discovery status and statistics"""
        stats = self.database.get_statistics()
        
        return {
            'total_plugins': stats['total_plugins'],
            'by_type': stats['by_type'],
            'by_category': stats['by_category'],
            'top_makers': stats['by_maker'],
            'cache_valid': self.database.is_cache_valid(),
            'discovery_tool_available': self.parser.is_discovery_tool_available()
        }