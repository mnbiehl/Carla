#!/usr/bin/env python3
"""
Test script for Carla MCP Dispatcher
"""

import asyncio
import logging
from carla_mcp_dispatcher.mcp_client import MCPClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_dispatcher():
    """Test the dispatcher functionality"""
    
    # Connect to dispatcher
    async with MCPClient(host="127.0.0.1", port=3000) as client:
        print("🔌 Testing connection to dispatcher...")
        
        # Get dispatcher status
        result = await client.call_tool("get_dispatcher_status", {})
        print(f"📊 Dispatcher status: {result}")
        
        # Create test instances
        print("\n🚀 Creating test instances...")
        
        for i in range(1, 4):
            instance_id = f"test{i}"
            print(f"\n  Creating instance: {instance_id}")
            result = await client.call_tool(
                "create_instance",
                {"instance_id": instance_id, "channels": 2}
            )
            print(f"  Result: {result}")
            
            if result.get("success"):
                print(f"  ✅ Instance created:")
                print(f"     - JACK name: {result.get('jack_name')}")
                print(f"     - MCP port: {result.get('mcp_port')}")
        
        # List instances
        print("\n📋 Listing all instances...")
        result = await client.call_tool("list_instances", {})
        print(f"Active instances: {result}")
        
        # Test plugin operations on first instance
        if result.get("count", 0) > 0:
            instance_id = "test1"
            print(f"\n🎛️  Testing plugin operations on {instance_id}...")
            
            # Add a plugin
            print(f"  Adding reverb plugin...")
            result = await client.call_tool(
                "add_plugin",
                {
                    "instance_id": instance_id,
                    "plugin_type": "internal",
                    "plugin_name": "Reverb"
                }
            )
            print(f"  Result: {result}")
            
            # List plugins
            print(f"\n  Listing plugins...")
            result = await client.call_tool(
                "list_plugins",
                {"instance_id": instance_id}
            )
            print(f"  Plugins: {result}")
            
            # Set parameter
            print(f"\n  Setting reverb room size...")
            result = await client.call_tool(
                "set_parameter",
                {
                    "instance_id": instance_id,
                    "plugin_id": 0,
                    "parameter_id": 0,
                    "value": 0.5
                }
            )
            print(f"  Result: {result}")
        
        # Test cleanup
        print("\n🧹 Cleaning up test instances...")
        for i in range(1, 4):
            instance_id = f"test{i}"
            print(f"  Destroying {instance_id}...")
            result = await client.call_tool(
                "destroy_instance",
                {"instance_id": instance_id}
            )
            print(f"  Result: {result}")
        
        # Final status
        print("\n📊 Final dispatcher status...")
        result = await client.call_tool("get_dispatcher_status", {})
        print(f"Status: {result}")


async def main():
    """Main test function"""
    print("🎵 Carla MCP Dispatcher Test")
    print("=" * 40)
    print("\nMake sure the dispatcher is running:")
    print("  python -m carla_mcp_dispatcher\n")
    
    input("Press Enter to start test...")
    
    try:
        await test_dispatcher()
        print("\n✅ Test completed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        logger.exception("Test error")


if __name__ == "__main__":
    asyncio.run(main())