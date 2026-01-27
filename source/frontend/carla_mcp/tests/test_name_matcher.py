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
