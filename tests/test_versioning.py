"""
Tests for the hybrid version matching engine.
"""
from dataclasses import dataclass
from typing import Optional
import pytest

from app.versioning.matching import (
    normalize_heading,
    get_node_path,
    generate_unified_diff,
    compare_versions,
)


# ── Minimal stub class to simulate a SQLAlchemy Node ──────────────────── #

@dataclass
class StubNode:
    id: str
    parent_id: Optional[str]
    heading: str
    level: int
    text: str
    content_hash: str
    sort_order: int


def _make_nodes(specs):
    """Helper: list of (id, parent_id, heading, level, text, hash) → StubNode list."""
    nodes = []
    for i, (nid, pid, heading, level, text, hsh) in enumerate(specs):
        nodes.append(StubNode(
            id=nid, parent_id=pid, heading=heading,
            level=level, text=text, content_hash=hsh, sort_order=i
        ))
    return nodes


class TestNormalizeHeading:
    def test_strips_bold(self):
        assert normalize_heading("**1.1 Intended Use**") == "intended use"

    def test_removes_leading_numbers(self):
        assert normalize_heading("2.1 General Specs") == "general specs"

    def test_lowercase(self):
        assert normalize_heading("Device Overview") == "device overview"

    def test_empty_string(self):
        assert normalize_heading("") == ""


class TestGetNodePath:
    def test_single_root_node(self):
        nodes = _make_nodes([("n1", None, "Device Overview", 1, "", "aaa")])
        by_id = {n.id: n for n in nodes}
        path = get_node_path("n1", by_id)
        assert path == "/device overview"

    def test_two_level_path(self):
        nodes = _make_nodes([
            ("n1", None, "Device Overview", 1, "", "aaa"),
            ("n2", "n1", "Intended Use", 2, "", "bbb"),
        ])
        by_id = {n.id: n for n in nodes}
        assert get_node_path("n2", by_id) == "/device overview/intended use"


class TestGenerateUnifiedDiff:
    def test_no_diff_on_identical_text(self):
        diff = generate_unified_diff("same text", "same text")
        assert diff == ""

    def test_diff_shows_additions(self):
        diff = generate_unified_diff("line a", "line a\nline b")
        assert "+line b" in diff

    def test_diff_shows_removals(self):
        diff = generate_unified_diff("line a\nline b", "line a")
        assert "-line b" in diff


class TestCompareVersions:
    def _simple_v1_v2(self):
        v1_nodes = _make_nodes([
            ("v1n1", None, "Device Overview", 1, "Oscillometric device.", "hash_ov"),
            ("v1n2", "v1n1", "Intended Use", 2, "For adults.", "hash_iu"),
            ("v1n3", "v1n1", "Contraindications", 2, "No IV lines.", "hash_ci"),
        ])
        # V2: same tree but 'Intended Use' body changed
        v2_nodes = _make_nodes([
            ("v2n1", None, "Device Overview", 1, "Oscillometric device.", "hash_ov"),
            ("v2n2", "v2n1", "Intended Use", 2, "For adults 18+.", "hash_iu_new"),
            ("v2n3", "v2n1", "Contraindications", 2, "No IV lines.", "hash_ci"),
        ])
        return v1_nodes, v2_nodes

    def test_summary_counts(self):
        v1, v2 = self._simple_v1_v2()
        mappings, summary = compare_versions(v1, v2)
        assert summary["unchanged_count"] == 2   # Overview + Contraindications
        assert summary["modified_count"] == 1    # Intended Use changed
        assert summary["deleted_count"] == 0
        assert summary["added_count"] == 0

    def test_modified_node_has_diff(self):
        v1, v2 = self._simple_v1_v2()
        mappings, _ = compare_versions(v1, v2)
        mod = next(m for m in mappings if m["comparison_status"] == "modified")
        assert mod["diff"] is not None
        assert "-For adults." in mod["diff"]

    def test_deleted_node_has_no_to_id(self):
        v1_nodes = _make_nodes([
            ("v1n1", None, "Overview", 1, "text", "h1"),
            ("v1n2", "v1n1", "Section A", 2, "text a", "h2"),
        ])
        v2_nodes = _make_nodes([
            ("v2n1", None, "Overview", 1, "text", "h1"),
            # Section A removed
        ])
        mappings, summary = compare_versions(v1_nodes, v2_nodes)
        deleted = [m for m in mappings if m["comparison_status"] == "deleted"]
        assert len(deleted) == 1
        assert deleted[0]["to_node_id"] is None
        assert summary["deleted_count"] == 1

    def test_added_nodes_counted_in_summary(self):
        v1_nodes = _make_nodes([
            ("v1n1", None, "Overview", 1, "text", "h1"),
        ])
        v2_nodes = _make_nodes([
            ("v2n1", None, "Overview", 1, "text", "h1"),
            ("v2n2", "v2n1", "New Section", 2, "new content", "h_new"),
        ])
        _, summary = compare_versions(v1_nodes, v2_nodes)
        assert summary["added_count"] == 1

    def test_title_similarity_fallback(self):
        """Nodes with very similar headings should be matched via similarity fallback."""
        v1_nodes = _make_nodes([
            ("v1n1", None, "Device Operation", 1, "Power on.", "h_op"),
        ])
        # V2 has a slightly renamed heading (typo fixed)
        v2_nodes = _make_nodes([
            ("v2n1", None, "Device Operations", 1, "Power on – revised.", "h_op_new"),
        ])
        mappings, summary = compare_versions(v1_nodes, v2_nodes)
        # Should be matched as modified (same heading-ish, different content)
        assert summary["modified_count"] == 1
        assert summary["added_count"] == 0
        assert summary["deleted_count"] == 0
