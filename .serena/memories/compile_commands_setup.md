# Compile Commands Setup for C++ Language Server

## Generating compile_commands.json

The Carla project uses Make as its primary build system. To generate `compile_commands.json` for better C++ language server support:

1. **Install compiledb**:
   ```bash
   pipx install compiledb
   ```

2. **Generate the compilation database**:
   ```bash
   make clean
   compiledb make -j4
   ```

3. **Restart language server** (if using Serena MCP):
   ```bash
   # In Serena, use the restart_language_server tool
   ```

## Benefits
With `compile_commands.json`, the C++ language server provides:
- Accurate symbol resolution
- Proper include path handling  
- Macro expansion understanding
- Cross-compilation unit navigation
- Template instantiation tracking

## Location
The `compile_commands.json` file is generated in the project root directory.

## Updating
Regenerate `compile_commands.json` when:
- Adding new source files
- Changing compiler flags
- Modifying include paths
- Updating build configuration