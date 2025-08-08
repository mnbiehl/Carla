# Code Style and Conventions

## C++ Code Style
- **License Headers**: SPDX-FileCopyrightText and SPDX-License-Identifier at file start
- **Include Guards**: Using #pragma once or traditional guards
- **Namespaces**: CARLA_BACKEND_START_NAMESPACE / CARLA_BACKEND_END_NAMESPACE macros
- **Class Naming**: PascalCase (e.g., CarlaPlugin, CarlaEngine)
- **Member Variables**: Prefixed with 'f' for fields (e.g., fPluginId, fActive)
- **Constants**: k-prefix for constants (e.g., kParameterDataNull)
- **Pointers**: Using nullptr instead of NULL
- **Comments**: Doxygen-style for documentation
- **Line separators**: Using // --- style separators for sections

## Python Code Style
- **Docstrings**: Triple quotes with module/function descriptions
- **Type Hints**: Using typing module (Union, Optional, etc.)
- **Global Variables**: Declared at module level with type hints
- **Error Handling**: Try-except blocks with specific error messages
- **Logging**: Using custom logging setup with emoji indicators (✅, ❌, ⚠️)
- **Function Decorators**: @mcp.tool() for MCP tool registration
- **Import Organization**: Standard library, third-party, then local imports
- **Line Length**: 79-100 characters (black formatter compatible)

## File Organization
- Source files in `source/` directory
- Backend code in `source/backend/`
- Frontend code in `source/frontend/`
- MCP server code in `source/frontend/carla_mcp/`
- Plugin discovery and tools organized in subdirectories
- Test files in `source/tests/` or root directory for integration tests

## Naming Conventions
- **Files**: snake_case for Python, PascalCase for C++ headers/sources
- **Functions**: snake_case in Python, camelCase in C++
- **Constants**: UPPER_SNAKE_CASE
- **Private Methods**: Leading underscore in Python