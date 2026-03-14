"""
Plugin database for storing and querying discovered plugins

Provides an in-memory database with search, filtering, and caching capabilities.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime

from .carla_discovery_parser import PluginInfo

logger = logging.getLogger(__name__)


class PluginDatabase:
    """In-memory plugin database with search and filtering capabilities"""
    
    def __init__(self, cache_file: Optional[str] = None):
        """
        Initialize plugin database
        
        Args:
            cache_file: Path to cache file for persistent storage
        """
        self.plugins: Dict[str, PluginInfo] = {}
        self.cache_file = cache_file or os.path.expanduser("~/.cache/carla-mcp-plugins.json")
        self.logger = logging.getLogger(__name__)
        
        # Ensure cache directory exists
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        
        # Load cached plugins
        self._load_cache()
    
    def add_plugin(self, plugin: PluginInfo) -> bool:
        """
        Add a plugin to the database
        
        Args:
            plugin: PluginInfo object to add
            
        Returns:
            True if plugin was added successfully
        """
        try:
            # Use plugin path as unique key
            key = plugin.plugin_path
            self.plugins[key] = plugin
            self.logger.debug(f"Added plugin: {plugin.name} ({plugin.plugin_path})")
            return True
        except Exception as e:
            self.logger.error(f"Error adding plugin {plugin.name}: {e}")
            return False
    
    def get_plugin(self, plugin_path: str) -> Optional[PluginInfo]:
        """
        Get a plugin by path
        
        Args:
            plugin_path: Path to plugin
            
        Returns:
            PluginInfo object or None if not found
        """
        return self.plugins.get(plugin_path)
    
    def get_all_plugins(self) -> List[PluginInfo]:
        """Get all plugins in the database"""
        return list(self.plugins.values())
    
    def search_plugins(self, query: str) -> List[PluginInfo]:
        """
        Search plugins by name, maker, or label
        
        Args:
            query: Search query string
            
        Returns:
            List of matching plugins
        """
        query_lower = query.lower()
        results = []
        
        for plugin in self.plugins.values():
            if (query_lower in plugin.name.lower() or
                query_lower in plugin.maker.lower() or
                query_lower in plugin.label.lower()):
                results.append(plugin)
        
        return results
    
    def filter_by_category(self, category: str) -> List[PluginInfo]:
        """
        Filter plugins by category
        
        Args:
            category: Plugin category to filter by
            
        Returns:
            List of plugins in the specified category
        """
        return [plugin for plugin in self.plugins.values() 
                if plugin.category.lower() == category.lower()]
    
    def filter_by_type(self, plugin_type: str) -> List[PluginInfo]:
        """
        Filter plugins by type
        
        Args:
            plugin_type: Plugin type to filter by (lv2, ladspa, vst2, etc.)
            
        Returns:
            List of plugins of the specified type
        """
        return [plugin for plugin in self.plugins.values()
                if plugin.plugin_type.lower() == plugin_type.lower()]
    
    def filter_by_maker(self, maker: str) -> List[PluginInfo]:
        """
        Filter plugins by maker/developer
        
        Args:
            maker: Plugin maker to filter by
            
        Returns:
            List of plugins by the specified maker
        """
        maker_lower = maker.lower()
        return [plugin for plugin in self.plugins.values()
                if maker_lower in plugin.maker.lower()]
    
    def filter_by_capabilities(self, 
                             audio_ins: Optional[int] = None,
                             audio_outs: Optional[int] = None,
                             midi_ins: Optional[int] = None,
                             midi_outs: Optional[int] = None) -> List[PluginInfo]:
        """
        Filter plugins by audio/MIDI capabilities
        
        Args:
            audio_ins: Required audio inputs (None = any)
            audio_outs: Required audio outputs (None = any)
            midi_ins: Required MIDI inputs (None = any)
            midi_outs: Required MIDI outputs (None = any)
            
        Returns:
            List of plugins matching the capability requirements
        """
        results = []
        
        for plugin in self.plugins.values():
            if (audio_ins is None or plugin.audio_ins >= audio_ins) and \
               (audio_outs is None or plugin.audio_outs >= audio_outs) and \
               (midi_ins is None or plugin.midi_ins >= midi_ins) and \
               (midi_outs is None or plugin.midi_outs >= midi_outs):
                results.append(plugin)
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        if not self.plugins:
            return {
                'total_plugins': 0,
                'by_type': {},
                'by_category': {},
                'by_maker': {}
            }
        
        # Count by type
        type_counts = {}
        category_counts = {}
        maker_counts = {}
        
        for plugin in self.plugins.values():
            # Count by type
            type_counts[plugin.plugin_type] = type_counts.get(plugin.plugin_type, 0) + 1
            
            # Count by category
            category_counts[plugin.category] = category_counts.get(plugin.category, 0) + 1
            
            # Count by maker
            maker_counts[plugin.maker] = maker_counts.get(plugin.maker, 0) + 1
        
        return {
            'total_plugins': len(self.plugins),
            'by_type': type_counts,
            'by_category': category_counts,
            'by_maker': dict(sorted(maker_counts.items(), key=lambda x: x[1], reverse=True)[:10])  # Top 10 makers
        }
    
    def get_categories(self) -> List[str]:
        """Get list of all categories present in the database"""
        categories = set()
        for plugin in self.plugins.values():
            categories.add(plugin.category)
        return sorted(list(categories))
    
    def get_makers(self) -> List[str]:
        """Get list of all makers present in the database"""
        makers = set()
        for plugin in self.plugins.values():
            makers.add(plugin.maker)
        return sorted(list(makers))
    
    def get_plugin_types(self) -> List[str]:
        """Get list of all plugin types present in the database"""
        types = set()
        for plugin in self.plugins.values():
            types.add(plugin.plugin_type)
        return sorted(list(types))
    
    def clear(self):
        """Clear all plugins from the database"""
        self.plugins.clear()
        self.logger.info("Plugin database cleared")
    
    def save_cache(self) -> bool:
        """
        Save plugin database to cache file
        
        Returns:
            True if saved successfully
        """
        try:
            # Convert plugins to serializable format
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'plugins': {path: plugin.to_dict() for path, plugin in self.plugins.items()}
            }
            
            # Write to cache file
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            self.logger.info(f"Saved {len(self.plugins)} plugins to cache: {self.cache_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving cache: {e}")
            return False
    
    def _load_cache(self) -> bool:
        """
        Load plugin database from cache file
        
        Returns:
            True if loaded successfully
        """
        try:
            if not os.path.exists(self.cache_file):
                self.logger.info("No cache file found, starting with empty database")
                return False
            
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Load plugins from cache
            plugins_data = cache_data.get('plugins', {})
            loaded_count = 0
            
            for path, plugin_data in plugins_data.items():
                try:
                    plugin = PluginInfo.from_dict(plugin_data)
                    self.plugins[path] = plugin
                    loaded_count += 1
                except Exception as e:
                    self.logger.warning(f"Error loading plugin from cache: {e}")
                    continue
            
            timestamp = cache_data.get('timestamp', 'unknown')
            self.logger.info(f"Loaded {loaded_count} plugins from cache (created: {timestamp})")
            return True
            
        except Exception as e:
            self.logger.error(f"Error loading cache: {e}")
            return False
    
    def is_cache_valid(self, max_age_days: int = 7) -> bool:
        """
        Check if the cache is valid (not too old)
        
        Args:
            max_age_days: Maximum age in days before cache is considered stale
            
        Returns:
            True if cache is valid
        """
        try:
            if not os.path.exists(self.cache_file):
                return False
            
            # Check file modification time
            mtime = os.path.getmtime(self.cache_file)
            age_days = (datetime.now().timestamp() - mtime) / (24 * 3600)
            
            return age_days < max_age_days
            
        except Exception as e:
            self.logger.error(f"Error checking cache validity: {e}")
            return False