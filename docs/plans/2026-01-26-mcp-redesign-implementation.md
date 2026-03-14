# Carla MCP Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the Python MCP layer with proper state management, multi-instance support, and high-level routing tools for live looping performance.

**Architecture:** Multi-instance Carla processes managed by a central MCP server with a State Manager that tracks connections, chains, and templates. The AI interacts with human-readable names; the State Manager resolves them to internal IDs.

**Tech Stack:** Python 3.10+, FastMCP, JACK (via `jack` Python bindings), subprocess for Carla instances, JSON for templates.

---

## Phase 1: Foundation

### Task 1: Create Test Infrastructure

**Files:**
- Create: `source/frontend/carla_mcp/tests/__init__.py`
- Create: `source/frontend/carla_mcp/tests/conftest.py`

**Step 1: Create tests directory and init file**

```bash
mkdir -p source/frontend/carla_mcp/tests
touch source/frontend/carla_mcp/tests/__init__.py
```

**Step 2: Create pytest conftest with fixtures**

Create `source/frontend/carla_mcp/tests/conftest.py`:

```python
"""Shared test fixtures for Carla MCP tests."""

import pytest
from unittest.mock import Mock, MagicMock


@pytest.fixture
def mock_jack_client():
    """Mock JACK client for testing without real JACK."""
    client = Mock()
    client.get_ports = Mock(return_value=[])
    client.connect = Mock()
    client.disconnect = Mock()
    return client


@pytest.fixture
def mock_carla_host():
    """Mock Carla host instance for testing without real Carla."""
    host = MagicMock()
    host.is_engine_running = Mock(return_value=True)
    host.get_current_plugin_count = Mock(return_value=0)
    host.add_plugin = Mock(return_value=True)
    host.remove_plugin = Mock(return_value=True)
    host.get_plugin_info = Mock(return_value={
        "name": "Test Plugin",
        "label": "test",
        "type": 4,  # LV2
    })
    return host
```

**Step 3: Verify pytest runs**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/ -v --collect-only`

Expected: Shows conftest.py loaded, 0 tests collected

**Step 4: Commit**

```bash
git add source/frontend/carla_mcp/tests/
git commit -m "test: Add test infrastructure with mock fixtures"
```

---

### Task 2: State Manager - Core Data Structures

**Files:**
- Create: `source/frontend/carla_mcp/state/__init__.py`
- Create: `source/frontend/carla_mcp/state/state_manager.py`
- Create: `source/frontend/carla_mcp/tests/test_state_manager.py`

**Step 1: Write the failing test for StateManager initialization**

Create `source/frontend/carla_mcp/tests/test_state_manager.py`:

```python
"""Tests for StateManager core functionality."""

import pytest
from carla_mcp.state.state_manager import StateManager


class TestStateManagerInit:
    """Test StateManager initialization."""

    def test_creates_empty_state(self):
        """StateManager initializes with empty collections."""
        sm = StateManager()

        assert sm.instances == {}
        assert sm.aliases == {}
        assert sm.chains == {}
        assert sm.connections == set()
```

**Step 2: Run test to verify it fails**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_state_manager.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'carla_mcp.state'"

**Step 3: Create state package and StateManager**

Create `source/frontend/carla_mcp/state/__init__.py`:

```python
"""State management for Carla MCP."""

from .state_manager import StateManager

__all__ = ["StateManager"]
```

Create `source/frontend/carla_mcp/state/state_manager.py`:

```python
"""
Central state manager for Carla MCP.

Tracks instances, aliases, chains, and connections so the AI
doesn't have to deal with internal IDs.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Tuple


@dataclass
class StateManager:
    """Manages all MCP state: instances, aliases, chains, connections."""

    instances: Dict[str, "CarlaInstance"] = field(default_factory=dict)
    aliases: Dict[str, str] = field(default_factory=dict)  # alias -> real_name
    chains: Dict[str, "Chain"] = field(default_factory=dict)
    connections: Set[Tuple[str, str]] = field(default_factory=set)  # (source, dest)
```

**Step 4: Run test to verify it passes**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_state_manager.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add source/frontend/carla_mcp/state/ source/frontend/carla_mcp/tests/test_state_manager.py
git commit -m "feat: Add StateManager with core data structures"
```

---

### Task 3: State Manager - Alias Operations

**Files:**
- Modify: `source/frontend/carla_mcp/state/state_manager.py`
- Modify: `source/frontend/carla_mcp/tests/test_state_manager.py`

**Step 1: Write failing tests for alias operations**

Add to `source/frontend/carla_mcp/tests/test_state_manager.py`:

```python
class TestAliasOperations:
    """Test alias create/remove/resolve."""

    def test_create_alias(self):
        """Can create an alias for a port name."""
        sm = StateManager()
        sm.create_alias("Guitar Loop", "looper:out_1")

        assert sm.aliases["Guitar Loop"] == "looper:out_1"

    def test_remove_alias(self):
        """Can remove an existing alias."""
        sm = StateManager()
        sm.create_alias("Guitar Loop", "looper:out_1")
        sm.remove_alias("Guitar Loop")

        assert "Guitar Loop" not in sm.aliases

    def test_resolve_alias(self):
        """resolve_name returns real name for alias."""
        sm = StateManager()
        sm.create_alias("Guitar Loop", "looper:out_1")

        assert sm.resolve_name("Guitar Loop") == "looper:out_1"

    def test_resolve_non_alias(self):
        """resolve_name returns input unchanged if not an alias."""
        sm = StateManager()

        assert sm.resolve_name("looper:out_1") == "looper:out_1"

    def test_list_aliases(self):
        """list_aliases returns all aliases."""
        sm = StateManager()
        sm.create_alias("Guitar", "looper:out_1")
        sm.create_alias("Bass", "looper:out_2")

        aliases = sm.list_aliases()
        assert aliases == {"Guitar": "looper:out_1", "Bass": "looper:out_2"}
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_state_manager.py::TestAliasOperations -v`

Expected: FAIL with "AttributeError: 'StateManager' object has no attribute 'create_alias'"

**Step 3: Implement alias methods**

Add to `source/frontend/carla_mcp/state/state_manager.py`:

```python
@dataclass
class StateManager:
    """Manages all MCP state: instances, aliases, chains, connections."""

    instances: Dict[str, "CarlaInstance"] = field(default_factory=dict)
    aliases: Dict[str, str] = field(default_factory=dict)
    chains: Dict[str, "Chain"] = field(default_factory=dict)
    connections: Set[Tuple[str, str]] = field(default_factory=set)

    def create_alias(self, alias: str, target: str) -> None:
        """Create an alias for a port/plugin name."""
        self.aliases[alias] = target

    def remove_alias(self, alias: str) -> None:
        """Remove an alias."""
        self.aliases.pop(alias, None)

    def resolve_name(self, name: str) -> str:
        """Resolve an alias to its real name, or return unchanged."""
        return self.aliases.get(name, name)

    def list_aliases(self) -> Dict[str, str]:
        """Return all aliases."""
        return dict(self.aliases)
```

**Step 4: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_state_manager.py::TestAliasOperations -v`

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add source/frontend/carla_mcp/state/state_manager.py source/frontend/carla_mcp/tests/test_state_manager.py
git commit -m "feat: Add alias operations to StateManager"
```

---

### Task 4: Stereo Pair Detection

**Files:**
- Create: `source/frontend/carla_mcp/state/stereo.py`
- Create: `source/frontend/carla_mcp/tests/test_stereo.py`

**Step 1: Write failing tests for stereo detection**

Create `source/frontend/carla_mcp/tests/test_stereo.py`:

```python
"""Tests for stereo pair detection and handling."""

import pytest
from carla_mcp.state.stereo import (
    is_stereo_pair,
    get_stereo_pair,
    get_channel_type,
    split_stereo_name,
)


class TestStereoPairDetection:
    """Test detection of stereo pairs from port names."""

    def test_detects_L_R_suffix(self):
        """Detects _L/_R as stereo pair."""
        assert is_stereo_pair("looper:out_1_L", "looper:out_1_R")

    def test_detects_left_right_suffix(self):
        """Detects _left/_right as stereo pair."""
        assert is_stereo_pair("plugin:out_left", "plugin:out_right")

    def test_rejects_non_pair(self):
        """Rejects ports that aren't a stereo pair."""
        assert not is_stereo_pair("looper:out_1_L", "looper:out_2_L")

    def test_get_stereo_pair_from_left(self):
        """Given left port, returns (left, right) tuple."""
        left, right = get_stereo_pair("looper:out_1_L")
        assert left == "looper:out_1_L"
        assert right == "looper:out_1_R"

    def test_get_stereo_pair_from_right(self):
        """Given right port, returns (left, right) tuple."""
        left, right = get_stereo_pair("looper:out_1_R")
        assert left == "looper:out_1_L"
        assert right == "looper:out_1_R"

    def test_get_channel_type_left(self):
        """Identifies left channel."""
        assert get_channel_type("port_L") == "left"
        assert get_channel_type("port_left") == "left"

    def test_get_channel_type_right(self):
        """Identifies right channel."""
        assert get_channel_type("port_R") == "right"
        assert get_channel_type("port_right") == "right"

    def test_get_channel_type_mono(self):
        """Returns mono for non-stereo ports."""
        assert get_channel_type("port_mono") == "mono"
        assert get_channel_type("port") == "mono"

    def test_split_stereo_name(self):
        """Splits stereo port name into base and channel."""
        base, channel = split_stereo_name("looper:out_1_L")
        assert base == "looper:out_1"
        assert channel == "L"
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_stereo.py -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement stereo detection**

Create `source/frontend/carla_mcp/state/stereo.py`:

```python
"""
Stereo pair detection and handling.

Recognizes common stereo naming conventions:
- _L / _R
- _left / _right
- _1 / _2 (context dependent)
"""

import re
from typing import Tuple, Optional, Literal

ChannelType = Literal["left", "right", "mono"]

# Patterns for stereo channel detection
LEFT_PATTERNS = [r"_L$", r"_left$", r"_l$"]
RIGHT_PATTERNS = [r"_R$", r"_right$", r"_r$"]


def get_channel_type(port_name: str) -> ChannelType:
    """Determine if port is left, right, or mono."""
    for pattern in LEFT_PATTERNS:
        if re.search(pattern, port_name, re.IGNORECASE):
            return "left"
    for pattern in RIGHT_PATTERNS:
        if re.search(pattern, port_name, re.IGNORECASE):
            return "right"
    return "mono"


def split_stereo_name(port_name: str) -> Tuple[str, Optional[str]]:
    """Split port name into base and channel suffix.

    Returns:
        (base_name, channel_suffix) or (port_name, None) if mono
    """
    for pattern in LEFT_PATTERNS + RIGHT_PATTERNS:
        match = re.search(pattern, port_name, re.IGNORECASE)
        if match:
            base = port_name[:match.start()]
            suffix = port_name[match.start() + 1:]  # Skip underscore
            return base, suffix
    return port_name, None


def get_stereo_pair(port_name: str) -> Tuple[str, str]:
    """Given one channel of a stereo pair, return (left, right).

    Args:
        port_name: Either channel of a stereo pair

    Returns:
        Tuple of (left_port, right_port)
    """
    base, suffix = split_stereo_name(port_name)
    if suffix is None:
        raise ValueError(f"Port {port_name} is not part of a stereo pair")

    # Preserve case of original suffix
    if suffix.isupper():
        return f"{base}_L", f"{base}_R"
    elif suffix == "left":
        return f"{base}_left", f"{base}_right"
    elif suffix == "right":
        return f"{base}_left", f"{base}_right"
    else:
        return f"{base}_l", f"{base}_r"


def is_stereo_pair(port_a: str, port_b: str) -> bool:
    """Check if two ports form a stereo pair."""
    type_a = get_channel_type(port_a)
    type_b = get_channel_type(port_b)

    # Must be one left and one right
    if not ((type_a == "left" and type_b == "right") or
            (type_a == "right" and type_b == "left")):
        return False

    # Must have same base name
    base_a, _ = split_stereo_name(port_a)
    base_b, _ = split_stereo_name(port_b)

    return base_a == base_b
```

**Step 4: Update state/__init__.py**

Add to `source/frontend/carla_mcp/state/__init__.py`:

```python
"""State management for Carla MCP."""

from .state_manager import StateManager
from .stereo import is_stereo_pair, get_stereo_pair, get_channel_type, split_stereo_name

__all__ = [
    "StateManager",
    "is_stereo_pair",
    "get_stereo_pair",
    "get_channel_type",
    "split_stereo_name",
]
```

**Step 5: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_stereo.py -v`

Expected: All 10 tests PASS

**Step 6: Commit**

```bash
git add source/frontend/carla_mcp/state/stereo.py source/frontend/carla_mcp/state/__init__.py source/frontend/carla_mcp/tests/test_stereo.py
git commit -m "feat: Add stereo pair detection"
```

---

### Task 5: Port Name Matching

**Files:**
- Create: `source/frontend/carla_mcp/state/name_matcher.py`
- Create: `source/frontend/carla_mcp/tests/test_name_matcher.py`

**Step 1: Write failing tests for name matching**

Create `source/frontend/carla_mcp/tests/test_name_matcher.py`:

```python
"""Tests for port name matching."""

import pytest
from carla_mcp.state.name_matcher import NameMatcher, MatchResult


class TestExactMatching:
    """Test exact name matching."""

    def test_exact_match_returns_single_result(self):
        """Exact match returns immediately executable result."""
        available = ["looper:out_1_L", "looper:out_1_R", "looper:out_2_L"]
        matcher = NameMatcher(available)

        result = matcher.match("looper:out_1_L")

        assert result.is_exact
        assert result.matches == ["looper:out_1_L"]

    def test_no_match_returns_empty(self):
        """No match returns empty result."""
        available = ["looper:out_1_L"]
        matcher = NameMatcher(available)

        result = matcher.match("nonexistent")

        assert not result.is_exact
        assert result.matches == []


class TestFuzzyMatching:
    """Test partial/fuzzy name matching."""

    def test_partial_match_returns_candidates(self):
        """Partial match returns all candidates."""
        available = ["looper:out_1_L", "looper:out_1_R", "looper:out_2_L"]
        matcher = NameMatcher(available)

        result = matcher.match("looper:out_1")

        assert not result.is_exact
        assert "looper:out_1_L" in result.matches
        assert "looper:out_1_R" in result.matches
        assert "looper:out_2_L" not in result.matches

    def test_client_name_only_returns_all_ports(self):
        """Matching just client name returns all its ports."""
        available = ["looper:out_1_L", "looper:out_1_R", "reverb:in_L"]
        matcher = NameMatcher(available)

        result = matcher.match("looper")

        assert not result.is_exact
        assert len(result.matches) == 2
        assert "reverb:in_L" not in result.matches

    def test_case_insensitive_matching(self):
        """Matching is case insensitive."""
        available = ["Calf Reverb:In L", "Calf Reverb:In R"]
        matcher = NameMatcher(available)

        result = matcher.match("calf reverb")

        assert len(result.matches) == 2
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_name_matcher.py -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement NameMatcher**

Create `source/frontend/carla_mcp/state/name_matcher.py`:

```python
"""
Port name matching with fuzzy/partial support.

Exact names execute immediately.
Partial names return candidates for user confirmation.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class MatchResult:
    """Result of a name match attempt."""

    query: str
    matches: List[str]
    is_exact: bool

    @property
    def needs_confirmation(self) -> bool:
        """True if multiple matches require user to pick one."""
        return not self.is_exact and len(self.matches) > 1


class NameMatcher:
    """Matches port names with exact and fuzzy matching."""

    def __init__(self, available_names: List[str]):
        """Initialize with list of available port names."""
        self.available = available_names
        self.available_lower = [n.lower() for n in available_names]

    def match(self, query: str) -> MatchResult:
        """Match a query against available names.

        Args:
            query: Port name to match (exact or partial)

        Returns:
            MatchResult with matches and whether it's exact
        """
        # Try exact match first
        if query in self.available:
            return MatchResult(query=query, matches=[query], is_exact=True)

        # Try case-insensitive exact match
        query_lower = query.lower()
        for i, name_lower in enumerate(self.available_lower):
            if name_lower == query_lower:
                return MatchResult(
                    query=query,
                    matches=[self.available[i]],
                    is_exact=True
                )

        # Fuzzy match: find all names containing the query
        matches = []
        for i, name_lower in enumerate(self.available_lower):
            if query_lower in name_lower:
                matches.append(self.available[i])

        # Also match if query is prefix of client name (before colon)
        for i, name in enumerate(self.available):
            if ":" in name:
                client = name.split(":")[0]
                if client.lower() == query_lower:
                    if self.available[i] not in matches:
                        matches.append(self.available[i])

        return MatchResult(query=query, matches=matches, is_exact=False)
```

**Step 4: Update state/__init__.py**

Add to exports in `source/frontend/carla_mcp/state/__init__.py`:

```python
from .name_matcher import NameMatcher, MatchResult

__all__ = [
    "StateManager",
    "is_stereo_pair",
    "get_stereo_pair",
    "get_channel_type",
    "split_stereo_name",
    "NameMatcher",
    "MatchResult",
]
```

**Step 5: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_name_matcher.py -v`

Expected: All 5 tests PASS

**Step 6: Commit**

```bash
git add source/frontend/carla_mcp/state/name_matcher.py source/frontend/carla_mcp/state/__init__.py source/frontend/carla_mcp/tests/test_name_matcher.py
git commit -m "feat: Add port name matching with fuzzy support"
```

---

### Task 6: Connection Tracking

**Files:**
- Modify: `source/frontend/carla_mcp/state/state_manager.py`
- Modify: `source/frontend/carla_mcp/tests/test_state_manager.py`

**Step 1: Write failing tests for connection tracking**

Add to `source/frontend/carla_mcp/tests/test_state_manager.py`:

```python
class TestConnectionTracking:
    """Test connection add/remove/query."""

    def test_add_connection(self):
        """Can add a connection."""
        sm = StateManager()
        sm.add_connection("looper:out_1_L", "reverb:in_L")

        assert ("looper:out_1_L", "reverb:in_L") in sm.connections

    def test_remove_connection(self):
        """Can remove a connection."""
        sm = StateManager()
        sm.add_connection("looper:out_1_L", "reverb:in_L")
        sm.remove_connection("looper:out_1_L", "reverb:in_L")

        assert ("looper:out_1_L", "reverb:in_L") not in sm.connections

    def test_list_connections(self):
        """Can list all connections."""
        sm = StateManager()
        sm.add_connection("looper:out_1_L", "reverb:in_L")
        sm.add_connection("looper:out_1_R", "reverb:in_R")

        conns = sm.list_connections()
        assert len(conns) == 2

    def test_get_connections_from(self):
        """Can get all connections from a source."""
        sm = StateManager()
        sm.add_connection("looper:out_1_L", "reverb:in_L")
        sm.add_connection("looper:out_1_L", "delay:in_L")
        sm.add_connection("looper:out_2_L", "chorus:in_L")

        conns = sm.get_connections_from("looper:out_1_L")
        assert len(conns) == 2
        assert "reverb:in_L" in conns
        assert "delay:in_L" in conns

    def test_get_connections_to(self):
        """Can get all connections to a destination."""
        sm = StateManager()
        sm.add_connection("looper:out_1_L", "reverb:in_L")
        sm.add_connection("looper:out_2_L", "reverb:in_L")

        conns = sm.get_connections_to("reverb:in_L")
        assert len(conns) == 2
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_state_manager.py::TestConnectionTracking -v`

Expected: FAIL with "AttributeError"

**Step 3: Implement connection methods**

Update `source/frontend/carla_mcp/state/state_manager.py`:

```python
"""
Central state manager for Carla MCP.

Tracks instances, aliases, chains, and connections so the AI
doesn't have to deal with internal IDs.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Tuple, List


@dataclass
class StateManager:
    """Manages all MCP state: instances, aliases, chains, connections."""

    instances: Dict[str, "CarlaInstance"] = field(default_factory=dict)
    aliases: Dict[str, str] = field(default_factory=dict)
    chains: Dict[str, "Chain"] = field(default_factory=dict)
    connections: Set[Tuple[str, str]] = field(default_factory=set)

    # Alias operations

    def create_alias(self, alias: str, target: str) -> None:
        """Create an alias for a port/plugin name."""
        self.aliases[alias] = target

    def remove_alias(self, alias: str) -> None:
        """Remove an alias."""
        self.aliases.pop(alias, None)

    def resolve_name(self, name: str) -> str:
        """Resolve an alias to its real name, or return unchanged."""
        return self.aliases.get(name, name)

    def list_aliases(self) -> Dict[str, str]:
        """Return all aliases."""
        return dict(self.aliases)

    # Connection operations

    def add_connection(self, source: str, destination: str) -> None:
        """Record a connection between source and destination."""
        self.connections.add((source, destination))

    def remove_connection(self, source: str, destination: str) -> None:
        """Remove a connection."""
        self.connections.discard((source, destination))

    def list_connections(self) -> List[Tuple[str, str]]:
        """Return all connections as list of (source, dest) tuples."""
        return list(self.connections)

    def get_connections_from(self, source: str) -> List[str]:
        """Get all destinations connected from a source."""
        return [dest for src, dest in self.connections if src == source]

    def get_connections_to(self, destination: str) -> List[str]:
        """Get all sources connected to a destination."""
        return [src for src, dest in self.connections if dest == destination]
```

**Step 4: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_state_manager.py::TestConnectionTracking -v`

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add source/frontend/carla_mcp/state/state_manager.py source/frontend/carla_mcp/tests/test_state_manager.py
git commit -m "feat: Add connection tracking to StateManager"
```

---

### Task 7: Chain Data Structure

**Files:**
- Create: `source/frontend/carla_mcp/state/chain.py`
- Create: `source/frontend/carla_mcp/tests/test_chain.py`

**Step 1: Write failing tests for Chain**

Create `source/frontend/carla_mcp/tests/test_chain.py`:

```python
"""Tests for Chain data structure."""

import pytest
from carla_mcp.state.chain import Chain


class TestChainCreation:
    """Test chain creation and properties."""

    def test_create_chain(self):
        """Can create a chain with name and components."""
        chain = Chain(
            name="Guitar FX",
            components=["looper:out_1", "Compressor", "Reverb", "system:playback"],
            instance="main"
        )

        assert chain.name == "Guitar FX"
        assert len(chain.components) == 4
        assert chain.instance == "main"

    def test_chain_generates_connections(self):
        """Chain generates connection pairs from components."""
        chain = Chain(
            name="Simple",
            components=["A", "B", "C"],
            instance="main"
        )

        connections = chain.get_connection_pairs()

        assert connections == [("A", "B"), ("B", "C")]

    def test_empty_chain_no_connections(self):
        """Chain with 0-1 components has no connections."""
        chain = Chain(name="Empty", components=[], instance="main")
        assert chain.get_connection_pairs() == []

        chain = Chain(name="Single", components=["A"], instance="main")
        assert chain.get_connection_pairs() == []

    def test_chain_source_and_dest(self):
        """Chain knows its source and destination."""
        chain = Chain(
            name="Test",
            components=["looper:out_1", "Reverb", "system:playback"],
            instance="main"
        )

        assert chain.source == "looper:out_1"
        assert chain.destination == "system:playback"
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_chain.py -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement Chain**

Create `source/frontend/carla_mcp/state/chain.py`:

```python
"""
Chain data structure for grouped audio routing.

A chain represents a signal path: source -> plugin1 -> plugin2 -> destination
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass
class Chain:
    """A named chain of audio components."""

    name: str
    components: List[str]  # Ordered list: source, plugins..., destination
    instance: str  # Which Carla instance this chain lives on

    def get_connection_pairs(self) -> List[Tuple[str, str]]:
        """Generate (source, dest) pairs for all connections in chain."""
        if len(self.components) < 2:
            return []

        pairs = []
        for i in range(len(self.components) - 1):
            pairs.append((self.components[i], self.components[i + 1]))
        return pairs

    @property
    def source(self) -> Optional[str]:
        """First component (audio source)."""
        return self.components[0] if self.components else None

    @property
    def destination(self) -> Optional[str]:
        """Last component (audio destination)."""
        return self.components[-1] if self.components else None
```

**Step 4: Update state/__init__.py**

Add to `source/frontend/carla_mcp/state/__init__.py`:

```python
from .chain import Chain

__all__ = [
    "StateManager",
    "is_stereo_pair",
    "get_stereo_pair",
    "get_channel_type",
    "split_stereo_name",
    "NameMatcher",
    "MatchResult",
    "Chain",
]
```

**Step 5: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_chain.py -v`

Expected: All 4 tests PASS

**Step 6: Commit**

```bash
git add source/frontend/carla_mcp/state/chain.py source/frontend/carla_mcp/state/__init__.py source/frontend/carla_mcp/tests/test_chain.py
git commit -m "feat: Add Chain data structure"
```

---

## Phase 2: Multi-Instance Management

### Task 8: Instance Manager - Data Structure

**Files:**
- Create: `source/frontend/carla_mcp/state/instance_manager.py`
- Create: `source/frontend/carla_mcp/tests/test_instance_manager.py`

**Step 1: Write failing tests for CarlaInstance**

Create `source/frontend/carla_mcp/tests/test_instance_manager.py`:

```python
"""Tests for multi-instance Carla management."""

import pytest
from unittest.mock import Mock, patch
from carla_mcp.state.instance_manager import CarlaInstance, InstanceManager


class TestCarlaInstance:
    """Test CarlaInstance data structure."""

    def test_instance_creation(self):
        """Can create instance with name."""
        instance = CarlaInstance(name="main", headless=True)

        assert instance.name == "main"
        assert instance.headless is True
        assert instance.process is None
        assert instance.host is None

    def test_instance_not_running_initially(self):
        """New instance is not running."""
        instance = CarlaInstance(name="test", headless=True)

        assert not instance.is_running


class TestInstanceManager:
    """Test InstanceManager operations."""

    def test_manager_starts_empty(self):
        """Manager starts with no instances."""
        manager = InstanceManager()

        assert manager.list_instances() == []

    def test_register_instance(self):
        """Can register an instance."""
        manager = InstanceManager()
        instance = CarlaInstance(name="main", headless=True)

        manager.register(instance)

        assert "main" in manager.list_instances()

    def test_get_instance(self):
        """Can retrieve instance by name."""
        manager = InstanceManager()
        instance = CarlaInstance(name="main", headless=True)
        manager.register(instance)

        retrieved = manager.get("main")

        assert retrieved is instance

    def test_get_nonexistent_returns_none(self):
        """Getting nonexistent instance returns None."""
        manager = InstanceManager()

        assert manager.get("nonexistent") is None
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_instance_manager.py -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement CarlaInstance and InstanceManager**

Create `source/frontend/carla_mcp/state/instance_manager.py`:

```python
"""
Multi-instance Carla management.

Each Carla instance runs as a separate process for parallel processing.
The InstanceManager tracks and controls all instances.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import subprocess


@dataclass
class CarlaInstance:
    """Represents a single Carla process."""

    name: str
    headless: bool = True
    process: Optional[subprocess.Popen] = None
    host: Optional[Any] = None  # CarlaHostDLL when connected
    jack_client_name: Optional[str] = None

    @property
    def is_running(self) -> bool:
        """Check if the Carla process is running."""
        if self.process is None:
            return False
        return self.process.poll() is None


class InstanceManager:
    """Manages multiple Carla instances."""

    def __init__(self):
        self._instances: Dict[str, CarlaInstance] = {}

    def register(self, instance: CarlaInstance) -> None:
        """Register an instance."""
        self._instances[instance.name] = instance

    def unregister(self, name: str) -> Optional[CarlaInstance]:
        """Unregister and return an instance."""
        return self._instances.pop(name, None)

    def get(self, name: str) -> Optional[CarlaInstance]:
        """Get instance by name."""
        return self._instances.get(name)

    def list_instances(self) -> List[str]:
        """List all instance names."""
        return list(self._instances.keys())

    def get_running(self) -> List[CarlaInstance]:
        """Get all running instances."""
        return [i for i in self._instances.values() if i.is_running]
```

**Step 4: Update state/__init__.py**

Add to `source/frontend/carla_mcp/state/__init__.py`:

```python
from .instance_manager import CarlaInstance, InstanceManager

__all__ = [
    "StateManager",
    "is_stereo_pair",
    "get_stereo_pair",
    "get_channel_type",
    "split_stereo_name",
    "NameMatcher",
    "MatchResult",
    "Chain",
    "CarlaInstance",
    "InstanceManager",
]
```

**Step 5: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_instance_manager.py -v`

Expected: All 6 tests PASS

**Step 6: Commit**

```bash
git add source/frontend/carla_mcp/state/instance_manager.py source/frontend/carla_mcp/state/__init__.py source/frontend/carla_mcp/tests/test_instance_manager.py
git commit -m "feat: Add CarlaInstance and InstanceManager"
```

---

### Task 9: JACK Port Discovery

**Files:**
- Create: `source/frontend/carla_mcp/state/jack_discovery.py`
- Create: `source/frontend/carla_mcp/tests/test_jack_discovery.py`

**Step 1: Write failing tests for JACK discovery**

Create `source/frontend/carla_mcp/tests/test_jack_discovery.py`:

```python
"""Tests for JACK port discovery."""

import pytest
from unittest.mock import Mock, patch
from carla_mcp.state.jack_discovery import JackDiscovery, PortInfo


class TestPortInfo:
    """Test PortInfo data structure."""

    def test_port_info_creation(self):
        """Can create PortInfo."""
        info = PortInfo(
            name="looper:out_1_L",
            client="looper",
            port="out_1_L",
            is_input=False,
            is_audio=True
        )

        assert info.name == "looper:out_1_L"
        assert info.client == "looper"
        assert not info.is_input
        assert info.is_audio


class TestJackDiscovery:
    """Test JACK port discovery with mocked JACK."""

    def test_list_audio_outputs(self, mock_jack_client):
        """Lists audio output ports."""
        mock_jack_client.get_ports.return_value = [
            Mock(name="looper:out_1_L", is_input=False, is_audio=True),
            Mock(name="looper:out_1_R", is_input=False, is_audio=True),
        ]

        discovery = JackDiscovery(mock_jack_client)
        outputs = discovery.get_audio_outputs()

        assert len(outputs) == 2
        assert outputs[0].name == "looper:out_1_L"

    def test_list_audio_inputs(self, mock_jack_client):
        """Lists audio input ports."""
        mock_jack_client.get_ports.return_value = [
            Mock(name="reverb:in_L", is_input=True, is_audio=True),
            Mock(name="reverb:in_R", is_input=True, is_audio=True),
        ]

        discovery = JackDiscovery(mock_jack_client)
        inputs = discovery.get_audio_inputs()

        assert len(inputs) == 2
        assert inputs[0].is_input is True

    def test_get_client_ports(self, mock_jack_client):
        """Gets all ports for a specific client."""
        mock_jack_client.get_ports.return_value = [
            Mock(name="looper:out_1_L", is_input=False, is_audio=True),
            Mock(name="looper:out_1_R", is_input=False, is_audio=True),
            Mock(name="reverb:in_L", is_input=True, is_audio=True),
        ]

        discovery = JackDiscovery(mock_jack_client)
        looper_ports = discovery.get_client_ports("looper")

        assert len(looper_ports) == 2
        assert all(p.client == "looper" for p in looper_ports)
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_jack_discovery.py -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement JackDiscovery**

Create `source/frontend/carla_mcp/state/jack_discovery.py`:

```python
"""
JACK port discovery.

Wraps JACK client to discover available audio ports.
"""

from dataclasses import dataclass
from typing import List, Optional, Any


@dataclass
class PortInfo:
    """Information about a JACK port."""

    name: str  # Full name: "client:port"
    client: str  # Client name
    port: str  # Port name within client
    is_input: bool
    is_audio: bool
    is_midi: bool = False


class JackDiscovery:
    """Discovers JACK ports."""

    def __init__(self, jack_client: Any):
        """Initialize with a JACK client.

        Args:
            jack_client: A jack.Client instance or mock
        """
        self._client = jack_client

    def _port_to_info(self, port: Any) -> PortInfo:
        """Convert JACK port object to PortInfo."""
        name = port.name
        client, port_name = name.split(":", 1) if ":" in name else (name, "")

        return PortInfo(
            name=name,
            client=client,
            port=port_name,
            is_input=port.is_input,
            is_audio=port.is_audio,
            is_midi=getattr(port, "is_midi", False)
        )

    def get_all_ports(self) -> List[PortInfo]:
        """Get all JACK ports."""
        ports = self._client.get_ports()
        return [self._port_to_info(p) for p in ports]

    def get_audio_outputs(self) -> List[PortInfo]:
        """Get all audio output ports."""
        ports = self._client.get_ports()
        return [
            self._port_to_info(p) for p in ports
            if p.is_audio and not p.is_input
        ]

    def get_audio_inputs(self) -> List[PortInfo]:
        """Get all audio input ports."""
        ports = self._client.get_ports()
        return [
            self._port_to_info(p) for p in ports
            if p.is_audio and p.is_input
        ]

    def get_client_ports(self, client_name: str) -> List[PortInfo]:
        """Get all ports for a specific JACK client."""
        all_ports = self.get_all_ports()
        return [p for p in all_ports if p.client == client_name]
```

**Step 4: Update state/__init__.py**

Add to `source/frontend/carla_mcp/state/__init__.py`:

```python
from .jack_discovery import JackDiscovery, PortInfo

__all__ = [
    # ... existing exports ...
    "JackDiscovery",
    "PortInfo",
]
```

**Step 5: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_jack_discovery.py -v`

Expected: All 4 tests PASS

**Step 6: Commit**

```bash
git add source/frontend/carla_mcp/state/jack_discovery.py source/frontend/carla_mcp/state/__init__.py source/frontend/carla_mcp/tests/test_jack_discovery.py
git commit -m "feat: Add JACK port discovery"
```

---

## Phase 3: New MCP Tools

### Task 10: Discovery Tools

**Files:**
- Create: `source/frontend/carla_mcp/tools_v2/__init__.py`
- Create: `source/frontend/carla_mcp/tools_v2/discovery.py`
- Create: `source/frontend/carla_mcp/tests/test_tools_discovery.py`

**Step 1: Write failing tests for discovery tools**

Create `source/frontend/carla_mcp/tests/test_tools_discovery.py`:

```python
"""Tests for new discovery MCP tools."""

import pytest
from unittest.mock import Mock
from carla_mcp.tools_v2.discovery import (
    list_ports,
    list_connections,
    list_instances,
)
from carla_mcp.state import StateManager, InstanceManager, CarlaInstance


@pytest.fixture
def state_manager():
    return StateManager()


@pytest.fixture
def instance_manager():
    return InstanceManager()


class TestListPorts:
    """Test list_ports tool."""

    def test_returns_grouped_ports(self, state_manager, mock_jack_client):
        """Returns ports grouped by type."""
        mock_jack_client.get_ports.return_value = [
            Mock(name="looper:out_1_L", is_input=False, is_audio=True),
            Mock(name="reverb:in_L", is_input=True, is_audio=True),
            Mock(name="system:playback_1", is_input=True, is_audio=True),
        ]

        result = list_ports(state_manager, mock_jack_client)

        assert "sources" in result
        assert "destinations" in result
        assert "looper:out_1_L" in result["sources"]


class TestListConnections:
    """Test list_connections tool."""

    def test_returns_all_connections(self, state_manager):
        """Returns all tracked connections."""
        state_manager.add_connection("looper:out_1_L", "reverb:in_L")
        state_manager.add_connection("reverb:out_L", "system:playback_1")

        result = list_connections(state_manager)

        assert len(result) == 2


class TestListInstances:
    """Test list_instances tool."""

    def test_returns_instance_info(self, instance_manager):
        """Returns info about all instances."""
        instance = CarlaInstance(name="main", headless=True)
        instance_manager.register(instance)

        result = list_instances(instance_manager)

        assert len(result) == 1
        assert result[0]["name"] == "main"
        assert result[0]["running"] is False
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_tools_discovery.py -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement discovery tools**

Create `source/frontend/carla_mcp/tools_v2/__init__.py`:

```python
"""New MCP tools (v2) with proper state management."""
```

Create `source/frontend/carla_mcp/tools_v2/discovery.py`:

```python
"""
Discovery tools for MCP.

These tools expose available ports, connections, and instances.
"""

from typing import Dict, List, Any
from ..state import StateManager, InstanceManager, JackDiscovery


def list_ports(state_manager: StateManager, jack_client: Any) -> Dict[str, List[str]]:
    """List all available JACK ports grouped by type.

    Returns:
        Dict with 'sources' (outputs) and 'destinations' (inputs)
    """
    discovery = JackDiscovery(jack_client)

    outputs = discovery.get_audio_outputs()
    inputs = discovery.get_audio_inputs()

    return {
        "sources": [p.name for p in outputs],
        "destinations": [p.name for p in inputs],
    }


def list_connections(state_manager: StateManager) -> List[Dict[str, str]]:
    """List all tracked connections.

    Returns:
        List of {"source": ..., "destination": ...} dicts
    """
    connections = state_manager.list_connections()
    return [{"source": src, "destination": dst} for src, dst in connections]


def list_instances(instance_manager: InstanceManager) -> List[Dict[str, Any]]:
    """List all Carla instances.

    Returns:
        List of instance info dicts
    """
    result = []
    for name in instance_manager.list_instances():
        instance = instance_manager.get(name)
        result.append({
            "name": name,
            "running": instance.is_running,
            "headless": instance.headless,
        })
    return result
```

**Step 4: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_tools_discovery.py -v`

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add source/frontend/carla_mcp/tools_v2/ source/frontend/carla_mcp/tests/test_tools_discovery.py
git commit -m "feat: Add discovery tools (list_ports, list_connections, list_instances)"
```

---

### Task 11: Connection Tools

**Files:**
- Create: `source/frontend/carla_mcp/tools_v2/routing.py`
- Create: `source/frontend/carla_mcp/tests/test_tools_routing.py`

**Step 1: Write failing tests for connect/disconnect**

Create `source/frontend/carla_mcp/tests/test_tools_routing.py`:

```python
"""Tests for routing MCP tools."""

import pytest
from unittest.mock import Mock, call
from carla_mcp.tools_v2.routing import connect, disconnect, ConnectResult
from carla_mcp.state import StateManager


@pytest.fixture
def state_manager():
    return StateManager()


@pytest.fixture
def mock_jack_client():
    client = Mock()
    client.connect = Mock()
    client.disconnect = Mock()
    client.get_ports = Mock(return_value=[
        Mock(name="looper:out_1_L", is_input=False, is_audio=True),
        Mock(name="looper:out_1_R", is_input=False, is_audio=True),
        Mock(name="reverb:in_L", is_input=True, is_audio=True),
        Mock(name="reverb:in_R", is_input=True, is_audio=True),
    ])
    return client


class TestConnect:
    """Test connect tool."""

    def test_exact_match_connects_immediately(self, state_manager, mock_jack_client):
        """Exact port names connect without confirmation."""
        result = connect(
            state_manager,
            mock_jack_client,
            source="looper:out_1_L",
            destination="reverb:in_L"
        )

        assert result.success
        assert result.needs_confirmation is False
        mock_jack_client.connect.assert_called_once()

    def test_connection_tracked_in_state(self, state_manager, mock_jack_client):
        """Successful connection is recorded in state."""
        connect(
            state_manager,
            mock_jack_client,
            source="looper:out_1_L",
            destination="reverb:in_L"
        )

        assert ("looper:out_1_L", "reverb:in_L") in state_manager.connections

    def test_partial_match_returns_candidates(self, state_manager, mock_jack_client):
        """Partial names return candidates for confirmation."""
        result = connect(
            state_manager,
            mock_jack_client,
            source="looper",
            destination="reverb"
        )

        assert not result.success
        assert result.needs_confirmation
        assert len(result.source_matches) > 0
        mock_jack_client.connect.assert_not_called()

    def test_stereo_auto_mode_connects_pair(self, state_manager, mock_jack_client):
        """Auto mode connects stereo pairs L→L, R→R."""
        result = connect(
            state_manager,
            mock_jack_client,
            source="looper:out_1",  # Stereo pair base name
            destination="reverb:in",
            mode="auto"
        )

        # Should make two connections
        assert mock_jack_client.connect.call_count == 2


class TestDisconnect:
    """Test disconnect tool."""

    def test_disconnect_removes_connection(self, state_manager, mock_jack_client):
        """Disconnect removes from JACK and state."""
        # First connect
        state_manager.add_connection("looper:out_1_L", "reverb:in_L")

        result = disconnect(
            state_manager,
            mock_jack_client,
            source="looper:out_1_L",
            destination="reverb:in_L"
        )

        assert result.success
        mock_jack_client.disconnect.assert_called_once()
        assert ("looper:out_1_L", "reverb:in_L") not in state_manager.connections
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_tools_routing.py -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement connect and disconnect**

Create `source/frontend/carla_mcp/tools_v2/routing.py`:

```python
"""
Routing tools for MCP.

Connect and disconnect audio ports with stereo awareness.
"""

from dataclasses import dataclass
from typing import List, Any, Optional
from ..state import StateManager, NameMatcher, JackDiscovery, get_stereo_pair, get_channel_type


@dataclass
class ConnectResult:
    """Result of a connect/disconnect operation."""

    success: bool
    message: str
    needs_confirmation: bool = False
    source_matches: List[str] = None
    destination_matches: List[str] = None

    def __post_init__(self):
        if self.source_matches is None:
            self.source_matches = []
        if self.destination_matches is None:
            self.destination_matches = []


def connect(
    state_manager: StateManager,
    jack_client: Any,
    source: str,
    destination: str,
    mode: str = "auto"
) -> ConnectResult:
    """Connect source to destination.

    Args:
        state_manager: State manager instance
        jack_client: JACK client for making connections
        source: Source port name (exact or partial)
        destination: Destination port name (exact or partial)
        mode: "auto" (smart stereo), "left", "right", "sum", "duplicate"

    Returns:
        ConnectResult with success status or candidates for confirmation
    """
    # Resolve aliases
    source = state_manager.resolve_name(source)
    destination = state_manager.resolve_name(destination)

    # Get available ports
    discovery = JackDiscovery(jack_client)
    outputs = [p.name for p in discovery.get_audio_outputs()]
    inputs = [p.name for p in discovery.get_audio_inputs()]

    # Match source
    source_matcher = NameMatcher(outputs)
    source_result = source_matcher.match(source)

    # Match destination
    dest_matcher = NameMatcher(inputs)
    dest_result = dest_matcher.match(destination)

    # If either needs confirmation, return candidates
    if source_result.needs_confirmation or dest_result.needs_confirmation:
        return ConnectResult(
            success=False,
            message="Multiple matches found. Please specify exact port names.",
            needs_confirmation=True,
            source_matches=source_result.matches,
            destination_matches=dest_result.matches
        )

    # If no matches, return error
    if not source_result.matches:
        return ConnectResult(
            success=False,
            message=f"No source port matching '{source}' found"
        )
    if not dest_result.matches:
        return ConnectResult(
            success=False,
            message=f"No destination port matching '{destination}' found"
        )

    # Handle stereo auto mode
    if mode == "auto":
        return _connect_auto(
            state_manager, jack_client,
            source_result.matches[0] if source_result.is_exact else source,
            dest_result.matches[0] if dest_result.is_exact else destination,
            outputs, inputs
        )

    # Single exact connection
    src_port = source_result.matches[0]
    dst_port = dest_result.matches[0]

    try:
        jack_client.connect(src_port, dst_port)
        state_manager.add_connection(src_port, dst_port)
        return ConnectResult(
            success=True,
            message=f"Connected {src_port} → {dst_port}"
        )
    except Exception as e:
        return ConnectResult(
            success=False,
            message=f"Connection failed: {e}"
        )


def _connect_auto(
    state_manager: StateManager,
    jack_client: Any,
    source: str,
    destination: str,
    available_outputs: List[str],
    available_inputs: List[str]
) -> ConnectResult:
    """Auto-connect with stereo pair detection."""
    # Check if source looks like a stereo base name
    source_l = f"{source}_L"
    source_r = f"{source}_R"
    dest_l = f"{destination}_L"
    dest_r = f"{destination}_R"

    has_stereo_source = source_l in available_outputs and source_r in available_outputs
    has_stereo_dest = dest_l in available_inputs and dest_r in available_inputs

    connections_made = []

    if has_stereo_source and has_stereo_dest:
        # Connect stereo pair
        try:
            jack_client.connect(source_l, dest_l)
            state_manager.add_connection(source_l, dest_l)
            connections_made.append(f"{source_l} → {dest_l}")

            jack_client.connect(source_r, dest_r)
            state_manager.add_connection(source_r, dest_r)
            connections_made.append(f"{source_r} → {dest_r}")

            return ConnectResult(
                success=True,
                message=f"Connected stereo pair: {', '.join(connections_made)}"
            )
        except Exception as e:
            return ConnectResult(success=False, message=f"Stereo connection failed: {e}")

    # Fall back to single connection if exact match exists
    if source in available_outputs and destination in available_inputs:
        try:
            jack_client.connect(source, destination)
            state_manager.add_connection(source, destination)
            return ConnectResult(success=True, message=f"Connected {source} → {destination}")
        except Exception as e:
            return ConnectResult(success=False, message=f"Connection failed: {e}")

    return ConnectResult(
        success=False,
        message=f"Could not find exact ports for '{source}' → '{destination}'"
    )


def disconnect(
    state_manager: StateManager,
    jack_client: Any,
    source: str,
    destination: str
) -> ConnectResult:
    """Disconnect source from destination.

    Args:
        state_manager: State manager instance
        jack_client: JACK client
        source: Source port name
        destination: Destination port name

    Returns:
        ConnectResult with success status
    """
    source = state_manager.resolve_name(source)
    destination = state_manager.resolve_name(destination)

    try:
        jack_client.disconnect(source, destination)
        state_manager.remove_connection(source, destination)
        return ConnectResult(
            success=True,
            message=f"Disconnected {source} → {destination}"
        )
    except Exception as e:
        return ConnectResult(
            success=False,
            message=f"Disconnect failed: {e}"
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_tools_routing.py -v`

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add source/frontend/carla_mcp/tools_v2/routing.py source/frontend/carla_mcp/tests/test_tools_routing.py
git commit -m "feat: Add connect and disconnect tools with stereo support"
```

---

### Task 12: Chain Tools

**Files:**
- Create: `source/frontend/carla_mcp/tools_v2/chains.py`
- Create: `source/frontend/carla_mcp/tests/test_tools_chains.py`

**Step 1: Write failing tests for create_chain and delete_chain**

Create `source/frontend/carla_mcp/tests/test_tools_chains.py`:

```python
"""Tests for chain MCP tools."""

import pytest
from unittest.mock import Mock
from carla_mcp.tools_v2.chains import create_chain, delete_chain, ChainResult
from carla_mcp.state import StateManager


@pytest.fixture
def state_manager():
    return StateManager()


@pytest.fixture
def mock_jack_client():
    client = Mock()
    client.connect = Mock()
    client.disconnect = Mock()
    client.get_ports = Mock(return_value=[
        Mock(name="looper:out_1_L", is_input=False, is_audio=True),
        Mock(name="looper:out_1_R", is_input=False, is_audio=True),
        Mock(name="Compressor:in_L", is_input=True, is_audio=True),
        Mock(name="Compressor:in_R", is_input=True, is_audio=True),
        Mock(name="Compressor:out_L", is_input=False, is_audio=True),
        Mock(name="Compressor:out_R", is_input=False, is_audio=True),
        Mock(name="system:playback_1", is_input=True, is_audio=True),
        Mock(name="system:playback_2", is_input=True, is_audio=True),
    ])
    return client


class TestCreateChain:
    """Test create_chain tool."""

    def test_creates_chain_with_connections(self, state_manager, mock_jack_client):
        """Creates chain and makes all connections."""
        result = create_chain(
            state_manager,
            mock_jack_client,
            name="Test Chain",
            components=["looper:out_1_L", "Compressor:in_L"],
            instance="main"
        )

        assert result.success
        assert "Test Chain" in state_manager.chains
        assert mock_jack_client.connect.called

    def test_chain_tracks_all_connections(self, state_manager, mock_jack_client):
        """Chain records all its connections in state."""
        create_chain(
            state_manager,
            mock_jack_client,
            name="Test",
            components=["looper:out_1_L", "Compressor:in_L"],
            instance="main"
        )

        chain = state_manager.chains["Test"]
        assert len(chain.components) == 2


class TestDeleteChain:
    """Test delete_chain tool."""

    def test_deletes_chain_and_connections(self, state_manager, mock_jack_client):
        """Deleting chain removes it and disconnects."""
        # First create a chain
        create_chain(
            state_manager,
            mock_jack_client,
            name="Test",
            components=["looper:out_1_L", "Compressor:in_L"],
            instance="main"
        )

        result = delete_chain(state_manager, mock_jack_client, name="Test")

        assert result.success
        assert "Test" not in state_manager.chains
        mock_jack_client.disconnect.assert_called()

    def test_delete_nonexistent_chain_fails(self, state_manager, mock_jack_client):
        """Deleting nonexistent chain returns error."""
        result = delete_chain(state_manager, mock_jack_client, name="Nonexistent")

        assert not result.success
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_tools_chains.py -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement chain tools**

Create `source/frontend/carla_mcp/tools_v2/chains.py`:

```python
"""
Chain tools for MCP.

Create and delete named routing chains.
"""

from dataclasses import dataclass
from typing import List, Any
from ..state import StateManager, Chain


@dataclass
class ChainResult:
    """Result of a chain operation."""

    success: bool
    message: str
    chain_name: str = ""


def create_chain(
    state_manager: StateManager,
    jack_client: Any,
    name: str,
    components: List[str],
    instance: str = "main"
) -> ChainResult:
    """Create a named chain and connect all components.

    Args:
        state_manager: State manager instance
        jack_client: JACK client for making connections
        name: Name for the chain
        components: Ordered list [source, plugin1, plugin2, ..., destination]
        instance: Which Carla instance this chain belongs to

    Returns:
        ChainResult with success status
    """
    if name in state_manager.chains:
        return ChainResult(
            success=False,
            message=f"Chain '{name}' already exists",
            chain_name=name
        )

    # Create chain object
    chain = Chain(name=name, components=components, instance=instance)

    # Make all connections
    connection_pairs = chain.get_connection_pairs()
    connected = []

    for source, dest in connection_pairs:
        try:
            jack_client.connect(source, dest)
            state_manager.add_connection(source, dest)
            connected.append(f"{source} → {dest}")
        except Exception as e:
            # Rollback on failure
            for src, dst in connected:
                try:
                    jack_client.disconnect(src.split(" → ")[0], src.split(" → ")[1])
                except:
                    pass
            return ChainResult(
                success=False,
                message=f"Chain creation failed at {source} → {dest}: {e}",
                chain_name=name
            )

    # Register chain in state
    state_manager.chains[name] = chain

    return ChainResult(
        success=True,
        message=f"Created chain '{name}' with {len(connected)} connections",
        chain_name=name
    )


def delete_chain(
    state_manager: StateManager,
    jack_client: Any,
    name: str
) -> ChainResult:
    """Delete a chain and disconnect all its connections.

    Args:
        state_manager: State manager instance
        jack_client: JACK client
        name: Name of chain to delete

    Returns:
        ChainResult with success status
    """
    if name not in state_manager.chains:
        return ChainResult(
            success=False,
            message=f"Chain '{name}' not found",
            chain_name=name
        )

    chain = state_manager.chains[name]

    # Disconnect all connections
    for source, dest in chain.get_connection_pairs():
        try:
            jack_client.disconnect(source, dest)
            state_manager.remove_connection(source, dest)
        except Exception:
            pass  # Best effort disconnection

    # Remove chain from state
    del state_manager.chains[name]

    return ChainResult(
        success=True,
        message=f"Deleted chain '{name}'",
        chain_name=name
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_tools_chains.py -v`

Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add source/frontend/carla_mcp/tools_v2/chains.py source/frontend/carla_mcp/tests/test_tools_chains.py
git commit -m "feat: Add create_chain and delete_chain tools"
```

---

## Phase 4: Template System

### Task 13: Template Manager

**Files:**
- Create: `source/frontend/carla_mcp/templates/__init__.py`
- Create: `source/frontend/carla_mcp/templates/template_manager.py`
- Create: `source/frontend/carla_mcp/tests/test_template_manager.py`

**Step 1: Write failing tests for template save/load**

Create `source/frontend/carla_mcp/tests/test_template_manager.py`:

```python
"""Tests for template manager."""

import pytest
import json
from pathlib import Path
from carla_mcp.templates.template_manager import TemplateManager, Template
from carla_mcp.state import StateManager, Chain


@pytest.fixture
def temp_template_dir(tmp_path):
    """Temporary directory for templates."""
    return tmp_path / "templates"


@pytest.fixture
def template_manager(temp_template_dir):
    return TemplateManager(template_dir=temp_template_dir)


@pytest.fixture
def state_with_data():
    """State manager with some data."""
    sm = StateManager()
    sm.create_alias("Guitar", "looper:out_1")
    sm.add_connection("looper:out_1_L", "reverb:in_L")
    sm.chains["Test Chain"] = Chain(
        name="Test Chain",
        components=["looper:out_1", "reverb", "system:playback"],
        instance="main"
    )
    return sm


class TestTemplateSave:
    """Test template saving."""

    def test_save_creates_file(self, template_manager, state_with_data, temp_template_dir):
        """Saving template creates JSON file."""
        template_manager.save("my-template", state_with_data)

        assert (temp_template_dir / "my-template.json").exists()

    def test_save_includes_aliases(self, template_manager, state_with_data):
        """Saved template includes aliases."""
        template_manager.save("test", state_with_data)
        template = template_manager.load("test")

        assert template.aliases == {"Guitar": "looper:out_1"}

    def test_save_includes_chains(self, template_manager, state_with_data):
        """Saved template includes chains."""
        template_manager.save("test", state_with_data)
        template = template_manager.load("test")

        assert "Test Chain" in template.chains


class TestTemplateLoad:
    """Test template loading."""

    def test_load_restores_aliases(self, template_manager, state_with_data):
        """Loading template restores aliases to state."""
        template_manager.save("test", state_with_data)

        new_state = StateManager()
        template_manager.apply("test", new_state)

        assert new_state.aliases == {"Guitar": "looper:out_1"}

    def test_load_nonexistent_raises(self, template_manager):
        """Loading nonexistent template raises error."""
        with pytest.raises(FileNotFoundError):
            template_manager.load("nonexistent")


class TestTemplateList:
    """Test template listing."""

    def test_list_templates(self, template_manager, state_with_data):
        """Lists all saved templates."""
        template_manager.save("template-a", state_with_data)
        template_manager.save("template-b", state_with_data)

        templates = template_manager.list_templates()

        assert "template-a" in templates
        assert "template-b" in templates
```

**Step 2: Run tests to verify they fail**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_template_manager.py -v`

Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement TemplateManager**

Create `source/frontend/carla_mcp/templates/__init__.py`:

```python
"""Template management for Carla MCP."""

from .template_manager import TemplateManager, Template

__all__ = ["TemplateManager", "Template"]
```

Create `source/frontend/carla_mcp/templates/template_manager.py`:

```python
"""
Template manager for saving and loading MCP configurations.

Templates are stored as JSON files in ~/.config/carla-mcp/templates/
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from ..state import StateManager, Chain


@dataclass
class Template:
    """A saved MCP configuration."""

    name: str
    created: str
    aliases: Dict[str, str]
    chains: Dict[str, Dict[str, Any]]  # Serialized Chain objects
    connections: List[List[str]]  # List of [source, dest] pairs


class TemplateManager:
    """Manages template save/load operations."""

    def __init__(self, template_dir: Optional[Path] = None):
        """Initialize template manager.

        Args:
            template_dir: Directory for templates. Defaults to ~/.config/carla-mcp/templates/
        """
        if template_dir is None:
            template_dir = Path.home() / ".config" / "carla-mcp" / "templates"

        self.template_dir = Path(template_dir)
        self.template_dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, state: StateManager) -> Path:
        """Save current state as a template.

        Args:
            name: Template name (used as filename)
            state: StateManager to save

        Returns:
            Path to saved template file
        """
        # Serialize chains
        chains_data = {}
        for chain_name, chain in state.chains.items():
            chains_data[chain_name] = {
                "name": chain.name,
                "components": chain.components,
                "instance": chain.instance,
            }

        template = Template(
            name=name,
            created=datetime.now().isoformat(),
            aliases=dict(state.aliases),
            chains=chains_data,
            connections=[[src, dst] for src, dst in state.connections],
        )

        filepath = self.template_dir / f"{name}.json"
        with open(filepath, "w") as f:
            json.dump(asdict(template), f, indent=2)

        return filepath

    def load(self, name: str) -> Template:
        """Load a template by name.

        Args:
            name: Template name

        Returns:
            Template object

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        filepath = self.template_dir / f"{name}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Template '{name}' not found at {filepath}")

        with open(filepath) as f:
            data = json.load(f)

        return Template(**data)

    def apply(self, name: str, state: StateManager, merge: bool = False) -> None:
        """Apply a template to state.

        Args:
            name: Template name
            state: StateManager to apply to
            merge: If True, merge with existing state. If False, replace.
        """
        template = self.load(name)

        if not merge:
            state.aliases.clear()
            state.chains.clear()
            state.connections.clear()

        # Restore aliases
        state.aliases.update(template.aliases)

        # Restore chains
        for chain_name, chain_data in template.chains.items():
            state.chains[chain_name] = Chain(
                name=chain_data["name"],
                components=chain_data["components"],
                instance=chain_data["instance"],
            )

        # Restore connections
        for src, dst in template.connections:
            state.connections.add((src, dst))

    def list_templates(self) -> List[str]:
        """List all saved templates.

        Returns:
            List of template names
        """
        templates = []
        for filepath in self.template_dir.glob("*.json"):
            templates.append(filepath.stem)
        return sorted(templates)

    def delete(self, name: str) -> bool:
        """Delete a template.

        Args:
            name: Template name

        Returns:
            True if deleted, False if not found
        """
        filepath = self.template_dir / f"{name}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False
```

**Step 4: Run tests to verify they pass**

Run: `cd source/frontend/carla_mcp && python -m pytest tests/test_template_manager.py -v`

Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add source/frontend/carla_mcp/templates/ source/frontend/carla_mcp/tests/test_template_manager.py
git commit -m "feat: Add template manager for save/load configurations"
```

---

## Phase 5: Integration & Cleanup

### Task 14: MCP Tool Registration

**Files:**
- Create: `source/frontend/carla_mcp/tools_v2/register.py`

**Step 1: Create tool registration module**

Create `source/frontend/carla_mcp/tools_v2/register.py`:

```python
"""
Register all v2 MCP tools with FastMCP server.

This replaces the old tool registration and uses the new state-aware tools.
"""

from typing import Any
from fastmcp import FastMCP

from ..state import StateManager, InstanceManager
from ..templates import TemplateManager
from .discovery import list_ports, list_connections, list_instances
from .routing import connect, disconnect
from .chains import create_chain, delete_chain


def register_v2_tools(
    mcp: FastMCP,
    state_manager: StateManager,
    instance_manager: InstanceManager,
    template_manager: TemplateManager,
    jack_client: Any
) -> None:
    """Register all v2 tools with the MCP server.

    Args:
        mcp: FastMCP server instance
        state_manager: Shared state manager
        instance_manager: Instance manager
        template_manager: Template manager
        jack_client: JACK client for audio routing
    """

    # Discovery tools

    @mcp.tool()
    def mcp_list_ports() -> dict:
        """List all available JACK audio ports.

        Returns grouped ports:
        - sources: Output ports (from loopers, plugins)
        - destinations: Input ports (plugin inputs, system playback)
        """
        return list_ports(state_manager, jack_client)

    @mcp.tool()
    def mcp_list_connections() -> list:
        """List all current audio connections.

        Returns list of {source, destination} pairs.
        """
        return list_connections(state_manager)

    @mcp.tool()
    def mcp_list_instances() -> list:
        """List all Carla instances.

        Returns info about each instance including running status.
        """
        return list_instances(instance_manager)

    # Routing tools

    @mcp.tool()
    def mcp_connect(source: str, destination: str, mode: str = "auto") -> dict:
        """Connect audio source to destination.

        Args:
            source: Source port name (exact or partial)
            destination: Destination port name (exact or partial)
            mode: Connection mode - "auto" (smart stereo), "left", "right"

        Returns:
            Result with success status. If partial names given, returns
            candidates for confirmation.
        """
        result = connect(state_manager, jack_client, source, destination, mode)
        return {
            "success": result.success,
            "message": result.message,
            "needs_confirmation": result.needs_confirmation,
            "source_matches": result.source_matches,
            "destination_matches": result.destination_matches,
        }

    @mcp.tool()
    def mcp_disconnect(source: str, destination: str) -> dict:
        """Disconnect audio source from destination.

        Args:
            source: Source port name
            destination: Destination port name
        """
        result = disconnect(state_manager, jack_client, source, destination)
        return {"success": result.success, "message": result.message}

    # Chain tools

    @mcp.tool()
    def mcp_create_chain(name: str, components: list, instance: str = "main") -> dict:
        """Create a named effects chain.

        Creates all connections between components in order.

        Args:
            name: Chain name
            components: Ordered list [source, plugin1, ..., destination]
            instance: Carla instance to use

        Example:
            create_chain("Guitar FX", ["looper:out_1", "Compressor", "Reverb", "system:playback"])
        """
        result = create_chain(state_manager, jack_client, name, components, instance)
        return {"success": result.success, "message": result.message}

    @mcp.tool()
    def mcp_delete_chain(name: str) -> dict:
        """Delete a chain and disconnect all its connections.

        Args:
            name: Chain name to delete
        """
        result = delete_chain(state_manager, jack_client, name)
        return {"success": result.success, "message": result.message}

    # Alias tools

    @mcp.tool()
    def mcp_create_alias(alias: str, target: str) -> dict:
        """Create an alias for a port name.

        Args:
            alias: Short name to use
            target: Full port name it refers to

        Example:
            create_alias("Guitar Loop", "looper:out_1")
        """
        state_manager.create_alias(alias, target)
        return {"success": True, "message": f"Created alias '{alias}' → '{target}'"}

    @mcp.tool()
    def mcp_remove_alias(alias: str) -> dict:
        """Remove an alias."""
        state_manager.remove_alias(alias)
        return {"success": True, "message": f"Removed alias '{alias}'"}

    @mcp.tool()
    def mcp_list_aliases() -> dict:
        """List all aliases."""
        return state_manager.list_aliases()

    # Template tools

    @mcp.tool()
    def mcp_save_template(name: str) -> dict:
        """Save current configuration as a template.

        Args:
            name: Template name
        """
        filepath = template_manager.save(name, state_manager)
        return {"success": True, "message": f"Saved template '{name}' to {filepath}"}

    @mcp.tool()
    def mcp_load_template(name: str, merge: bool = False) -> dict:
        """Load a saved template.

        Args:
            name: Template name
            merge: If true, merge with current state. Otherwise replace.
        """
        try:
            template_manager.apply(name, state_manager, merge=merge)
            return {"success": True, "message": f"Loaded template '{name}'"}
        except FileNotFoundError:
            return {"success": False, "message": f"Template '{name}' not found"}

    @mcp.tool()
    def mcp_list_templates() -> list:
        """List all saved templates."""
        return template_manager.list_templates()
```

**Step 2: Commit**

```bash
git add source/frontend/carla_mcp/tools_v2/register.py
git commit -m "feat: Add MCP tool registration for v2 tools"
```

---

### Task 15: Delete Unused C++ Parallel Code

**Files:**
- Delete: `source/backend/engine/CarlaEngineGraphParallelV2.cpp`
- Delete: `source/backend/engine/CarlaEngineGraphParallelV2.hpp`

**Step 1: Remove C++ parallel files**

```bash
git rm source/backend/engine/CarlaEngineGraphParallelV2.cpp
git rm source/backend/engine/CarlaEngineGraphParallelV2.hpp
```

**Step 2: Commit**

```bash
git commit -m "chore: Remove unused C++ parallel processing code

Multi-instance approach replaces in-process parallelism.
See docs/plans/2026-01-26-mcp-redesign.md for rationale."
```

---

### Task 16: Run Full Test Suite

**Step 1: Run all tests**

```bash
cd source/frontend/carla_mcp && python -m pytest tests/ -v
```

Expected: All tests PASS

**Step 2: Check test coverage**

```bash
cd source/frontend/carla_mcp && python -m pytest tests/ --cov=carla_mcp --cov-report=term-missing
```

Review coverage and note any gaps.

**Step 3: Final commit**

```bash
git add -A
git commit -m "test: Verify full test suite passes"
```

---

## Summary

**Tasks completed:**
1. Test infrastructure
2. StateManager core
3. Alias operations
4. Stereo pair detection
5. Port name matching
6. Connection tracking
7. Chain data structure
8. Instance manager
9. JACK port discovery
10. Discovery tools
11. Connection tools
12. Chain tools
13. Template manager
14. MCP tool registration
15. Delete C++ parallel code
16. Full test suite

**Files created:**
- `source/frontend/carla_mcp/state/` - State management package
- `source/frontend/carla_mcp/tools_v2/` - New MCP tools
- `source/frontend/carla_mcp/templates/` - Template system
- `source/frontend/carla_mcp/tests/` - Test suite

**Files deleted:**
- `source/backend/engine/CarlaEngineGraphParallelV2.cpp`
- `source/backend/engine/CarlaEngineGraphParallelV2.hpp`

**Next steps after this plan:**
- Integrate v2 tools with main.py
- Manual testing with real looper + JACK
- Implement instance spawning (subprocess management)
