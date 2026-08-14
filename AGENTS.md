# Carla MCP Server

Carla MCP Server provides AI control over the Carla audio plugin host via the Model Context Protocol. Combines a C++ audio engine (Carla) with a Python MCP frontend using FastMCP.

## Tech Stack & Build

- **Dev script:** `./dev run|mcp|build|test` — preferred entry point for common tasks
- **C++ backend:** `make -j$(nproc)` (release) or `make DEBUG=true -j$(nproc)` (debug)
- **Python frontend:** `uv sync` to install, `uv run python -m carla_mcp.main` to run
- **Tests:** `uv run pytest` (Python), `make tests` (C++)
- **Package manager:** uv (Python), Make (C++)

## Knowledge Base

All project knowledge lives in `kb/` (git submodule, shared across branches).
**Never** place design docs, plans, decisions, or ideas outside `kb/`.

| What | Where |
|------|-------|
| Golden principles | `kb/Carla/golden-principles.md` |
| Architecture | `kb/Carla/architecture/` |
| Design documents | `kb/Carla/design-docs/` |
| Active plans | `kb/Carla/exec-plans/active/` |
| Quality scores | `kb/Carla/quality-scores.md` |
| Tech debt | `kb/Carla/tech-debt/` |
| Product specs | `kb/Carla/product-specs/` |
| Ideas | `kb/Carla/ideas/` |

Where `Carla` is derived from `git remote origin`.

## CLI

Use `rcorn` for all kb operations.

| Command | Purpose |
|---------|---------|
| `rcorn kb sync` | Pull latest kb state |
| `rcorn kb publish` | Push kb changes |
| `rcorn <spec\|prd\|debt\|idea> create "title"` | Create kb doc from template |
| `rcorn kb status` | Kb health + cross-branch overlap |
| `rcorn plan create` | Create execution plan for current branch |

## Project Conventions

- **C++:** PascalCase classes, camelCase methods, fPrefix for members, `nullptr` not `NULL`
- **Python:** snake_case, type hints, docstrings, 100 char lines
- **Imports:** stdlib -> third-party -> local, alphabetical within groups
- **LV2 plugin loading:** pass bundle directory path (not .so), empty filename, URI in label field
- **Patchbay port offsets:** inputs use offset 255, outputs use 510, multiplied by group_id * 1000
- **Constants:** always import from `carla_mcp/constants.py` (single source of truth)
- **Rig subsystem:** `source/frontend/carla_mcp/rig/` (graph/reconciler/session) is the
  primary control surface; design docs live in `kb/Carla/design-docs/`

## Hard Rules

1. **Check the plan first.** Read `kb/Carla/exec-plans/active/{branch}/plan.md`
   before writing code. No plan? Ask the developer.
2. **Never create kb docs directly.** Use `rcorn <spec|prd|debt|idea> create "title"`.
3. **Never manage the kb submodule with git directly.** Use
   `rcorn kb publish` to push, `rcorn kb sync` to pull.
4. **Follow golden principles.** Read `kb/Carla/golden-principles.md`.
5. **Run tests before marking work complete.** Write tests for new behavior.
6. **Conventional commits.** `type(scope): description`

## Progressive Disclosure

This file is a map. For details on any topic, read the linked kb document.
For maintenance procedures, run `rcorn` subcommands — the CLI encodes the
workflows.
