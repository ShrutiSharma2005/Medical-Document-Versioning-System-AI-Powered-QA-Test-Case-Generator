"""
Tests for the Markdown parser.
"""
import pytest
from app.parser.markdown_parser import parse_markdown_to_nodes, clean_heading_text

SAMPLE_MD = """\
# **Device Overview**

The CT-200 is an oscillometric monitor.

## **1.1 Intended Use**

Intended for adults aged 18+.

### **1.1.1 Indications**

Do not use on neonates.

|Param|Value|
|---|---|
|Accuracy|±3 mmHg|

## **1.2 Contraindications**

Not for use on limbs with IV lines.

#####

Some orphan paragraph.

# **Device Overview**

Duplicate heading – must get its own UUID.
"""

VERSION_ID = "test-version-001"


class TestParser:
    def test_returns_non_empty_list(self):
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        assert len(nodes) > 0

    def test_all_nodes_have_required_fields(self):
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        for node in nodes:
            assert "id" in node
            assert "version_id" in node
            assert "heading" in node
            assert "level" in node
            assert "text" in node
            assert "content_hash" in node
            assert "sort_order" in node

    def test_version_id_assigned_to_all_nodes(self):
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        for node in nodes:
            assert node["version_id"] == VERSION_ID

    def test_heading_levels_are_correct(self):
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        heading_map = {n["heading"]: n["level"] for n in nodes if n["heading"]}
        # "Device Overview" is level 1 in SAMPLE_MD
        device_nodes = [n for n in nodes if "Device Overview" in n["heading"]]
        assert all(n["level"] == 1 for n in device_nodes)

    def test_parent_child_relationship(self):
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        by_id = {n["id"]: n for n in nodes}
        indications = next((n for n in nodes if "Indications" in n["heading"]), None)
        assert indications is not None
        assert indications["parent_id"] is not None
        parent = by_id[indications["parent_id"]]
        assert "Intended Use" in parent["heading"]

    def test_duplicate_headings_get_unique_ids(self):
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        device_nodes = [n for n in nodes if n["heading"] == "Device Overview"]
        ids = [n["id"] for n in device_nodes]
        assert len(ids) == 2
        assert ids[0] != ids[1]

    def test_empty_heading_parsed(self):
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        empty_heading_nodes = [n for n in nodes if n["heading"] == "" and n["level"] == 5]
        assert len(empty_heading_nodes) >= 1

    def test_table_preserved_in_body(self):
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        # The table should appear in the text of some node
        all_text = " ".join(n["text"] for n in nodes)
        assert "±3 mmHg" in all_text

    def test_content_hashes_are_unique_per_node(self):
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        hashes = [n["content_hash"] for n in nodes]
        # Allow some collisions (e.g. empty nodes) but most should be distinct
        assert len(set(hashes)) >= len(hashes) * 0.8

    def test_sort_order_is_monotonically_increasing(self):
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        orders = [n["sort_order"] for n in nodes]
        assert orders == sorted(orders)

    def test_no_content_is_silently_lost(self):
        """Every significant line of text must appear somewhere in the tree."""
        nodes = parse_markdown_to_nodes(SAMPLE_MD, VERSION_ID)
        all_text = " ".join(n["text"] for n in nodes) + " ".join(n["heading"] for n in nodes)
        assert "oscillometric" in all_text
        assert "neonates" in all_text
        assert "IV lines" in all_text

    def test_no_heading_document(self):
        """A document with no headings should produce a single Intro node."""
        plain = "Just some text.\nMore text here."
        nodes = parse_markdown_to_nodes(plain, VERSION_ID)
        assert len(nodes) == 1
        assert nodes[0]["heading"] == "Intro"
        assert "Just some text" in nodes[0]["text"]


class TestCleanHeading:
    def test_removes_bold_markers(self):
        assert clean_heading_text("**Bold Heading**") == "Bold Heading"

    def test_strips_whitespace(self):
        assert clean_heading_text("  Heading  ") == "Heading"

    def test_empty_string(self):
        assert clean_heading_text("") == ""
