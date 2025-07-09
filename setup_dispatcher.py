#!/usr/bin/env python3
"""
Setup script for Carla MCP Dispatcher
"""

from setuptools import setup, find_packages

with open("carla_mcp_dispatcher/README.md", "r") as f:
    long_description = f.read()

setup(
    name="carla-mcp-dispatcher",
    version="0.1.0",
    description="Multi-instance Carla manager with MCP interface",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Carla MCP Team",
    packages=find_packages(),
    install_requires=[
        "fastmcp>=0.10.0",
        "aiohttp>=3.8.0",
        "python-osc>=1.8.0",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "carla-mcp-dispatcher=carla_mcp_dispatcher.dispatcher_server:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)