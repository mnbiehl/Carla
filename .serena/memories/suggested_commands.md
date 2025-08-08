# Suggested Commands for Development

## Build Commands
```bash
# Main build
make

# Clean build
make clean

# Build with debug symbols
make DEBUG=true

# Build specific targets
make backend
make frontend
make plugin

# Build tests
make tests

# Build documentation
make doxygen
```

## Testing Commands
```bash
# Run C++ tests
make tests
./source/tests/[test_name]

# Run Python tests
poetry run pytest
poetry run pytest -v  # verbose
poetry run pytest -k "test_name"  # specific test
```

## Linting and Formatting
```bash
# Python linting
poetry run flake8 source/frontend/
poetry run pylint source/frontend/carla_mcp/
poetry run black source/frontend/ --check  # check only
poetry run black source/frontend/  # format files

# For Travis CI style checking
.travis/script-pylint.sh
```

## Running Carla
```bash
# Run without installing
./source/frontend/carla

# Run with MCP server
poetry run carla-mcp

# Run specific Python scripts
poetry run python test_parallel_processing.py
```

## Installation
```bash
# Standard installation
sudo make install

# Custom prefix installation
make install PREFIX=/usr DESTDIR=./test-dir

# Check available features
make features
```

## Git Commands
```bash
git status
git diff
git add -p  # interactive staging
git commit -m "message"
git push origin branch-name
```

## Poetry Commands
```bash
poetry install  # install dependencies
poetry add package-name  # add new dependency
poetry run command  # run command in virtual env
poetry shell  # activate virtual environment
```

## System Utilities (Linux/Pop_OS)
```bash
ls -la  # list files with details
find . -name "*.py"  # find Python files
grep -r "pattern" .  # recursive search
rg "pattern"  # ripgrep (faster alternative)
```