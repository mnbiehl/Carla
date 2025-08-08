# Task Completion Checklist

When completing a development task in the Carla MCP project, follow these steps:

## Before Starting Work
1. Understand the requirements fully
2. Check existing code for similar implementations
3. Review relevant documentation

## During Development

### For C++ Code
1. Follow CARLA namespace conventions
2. Use appropriate license headers (SPDX)
3. Maintain consistent naming (PascalCase for classes, camelCase for methods)
4. Handle memory management properly (RAII, smart pointers where appropriate)
5. Ensure thread safety for audio processing code

### For Python Code
1. Add proper docstrings to functions and classes
2. Use type hints for function parameters and returns
3. Follow snake_case naming convention
4. Handle exceptions appropriately
5. Add logging for important operations

## After Code Changes

### 1. Build Verification
```bash
# For C++ changes
make clean
make

# For Python changes (if using compiled extensions)
poetry install
```

### 2. Code Quality Checks
```bash
# Python linting
poetry run flake8 source/frontend/carla_mcp/
poetry run black source/frontend/carla_mcp/ --check

# If linting fails, format the code:
poetry run black source/frontend/carla_mcp/
```

### 3. Testing
```bash
# Run relevant tests
make tests  # for C++ tests
poetry run pytest  # for Python tests

# Run specific test if working on particular feature
poetry run pytest -k "test_name"
```

### 4. Manual Testing
- Start Carla and verify the feature works
- Test edge cases and error conditions
- Check for performance regressions
- Verify no existing functionality is broken

### 5. Documentation
- Update relevant documentation if APIs changed
- Add comments for complex logic
- Update README if adding new features

## Before Committing
1. Review all changes with `git diff`
2. Stage changes selectively with `git add -p`
3. Write clear, descriptive commit messages
4. Reference issue numbers if applicable

## Common Issues to Check
- [ ] No hardcoded paths
- [ ] No debug print statements left in code
- [ ] Error messages are user-friendly
- [ ] New dependencies are added to pyproject.toml
- [ ] Code follows project style guidelines
- [ ] Tests pass locally
- [ ] No compiler warnings for C++ code