# Carla MCP Server

Carla MCP Server provides AI control over the Carla audio plugin host via the Model Context Protocol. Combines a C++ audio engine (Carla) with a Python MCP frontend using FastMCP.

## Tech Stack & Build

- **C++ backend:** `make -j$(nproc)` (release) or `make DEBUG=true -j$(nproc)` (debug)
- **Python frontend:** `uv sync` to install, `uv run python -m carla_mcp.main` to run
- **Tests:** `uv run pytest` (Python), `make tests` (C++)
- **Package manager:** uv (Python), Make (C++)

## Knowledge Base

All project knowledge lives in `harness/` (git submodule, shared across branches).
**Never** place design docs, plans, decisions, or ideas outside `harness/`.

| What | Where |
|------|-------|
| Golden principles | `harness/Carla/golden-principles.md` |
| Architecture | `harness/Carla/architecture/` |
| Design documents | `harness/Carla/design-docs/` |
| Active plans | `harness/Carla/exec-plans/active/` |
| Quality scores | `harness/Carla/quality-scores.md` |
| Tech debt | `harness/Carla/tech-debt/` |
| Product specs | `harness/Carla/product-specs/` |
| Ideas | `harness/Carla/ideas/` |

Where `Carla` is derived from `git remote origin`.

## CLI

Use `reinicorn` for all harness operations. Run via `uv run reinicorn`.

| Command | Purpose |
|---------|---------|
| `reinicorn sync` | Pull latest harness state |
| `reinicorn publish` | Push harness changes |
| `reinicorn doc create <type> "title"` | Create harness doc from template |
| `reinicorn status` | Harness health + cross-branch overlap |
| `reinicorn plan create` | Create execution plan for current branch |

## Project Conventions

- **C++:** PascalCase classes, camelCase methods, fPrefix for members, `nullptr` not `NULL`
- **Python:** snake_case, type hints, docstrings, 100 char lines
- **Imports:** stdlib -> third-party -> local, alphabetical within groups
- **LV2 plugin loading:** pass bundle directory path (not .so), empty filename, URI in label field
- **Patchbay port offsets:** inputs use offset 255, outputs use 510, multiplied by group_id * 1000
- **Constants:** always import from `carla_mcp/constants.py` (single source of truth)

## Hard Rules

1. **Check the plan first.** Read `harness/Carla/exec-plans/active/{branch}/plan.md`
   before writing code. No plan? Ask the developer.
2. **Never create harness docs directly.** Use `reinicorn doc create <type> "title"`.
3. **Never manage the harness submodule with git directly.** Use
   `reinicorn publish` to push, `reinicorn sync` to pull.
4. **Follow golden principles.** Read `harness/Carla/golden-principles.md`.
5. **Run tests before marking work complete.** Write tests for new behavior.
6. **Conventional commits.** `type(scope): description`

## Progressive Disclosure

This file is a map. For details on any topic, read the linked harness document.
For maintenance procedures, run `reinicorn` subcommands — the CLI encodes the
workflows.
