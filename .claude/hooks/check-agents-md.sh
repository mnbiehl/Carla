#!/bin/bash
# Check if AGENTS.md needs population.
# Runs on SessionStart — stdout is injected into agent context.
AGENTS_FILE="${CLAUDE_PROJECT_DIR:-.}/AGENTS.md"

if [ -f "$AGENTS_FILE" ] && grep -q '<!-- UNPOPULATED' "$AGENTS_FILE"; then
    echo "AGENTS.md has not been populated yet."
    echo "Run the populate-agents-md skill to analyze this repo and fill in project-specific sections."
fi

exit 0
