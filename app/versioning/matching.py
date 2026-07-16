import re
import difflib
from typing import List, Dict, Any, Tuple, Set, Optional
from loguru import logger

def normalize_heading(heading: str) -> str:
    """
    Normalizes heading text for robust comparison.
    1. Removes markdown symbols (*, **, `).
    2. Strips leading numbers (e.g., '1.2.1 Intended Use' -> 'Intended Use').
    3. Converts to lowercase.
    4. Removes non-alphanumeric/non-space characters.
    """
    # Remove markdown tags
    text = heading.replace("**", "").replace("*", "").replace("`", "").strip()
    # Remove leading numbering (e.g., '1.', '1.1', '2.1.1.1')
    text = re.sub(r'^\d+(\.\d+)*\s*', '', text)
    # Lowercase and clean special chars
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()

def get_node_path(node_id: str, nodes_by_id: Dict[str, Any]) -> str:
    """Builds a slash-separated string representing the normalized path of the node."""
    path_components = []
    curr_id = node_id
    visited = set()
    
    while curr_id and curr_id not in visited:
        visited.add(curr_id)
        node = nodes_by_id[curr_id]
        path_components.append(normalize_heading(node.heading))
        curr_id = node.parent_id
        
    return "/" + "/".join(reversed(path_components))

def generate_unified_diff(text1: str, text2: str) -> str:
    """Generates a unified text diff between two text blocks."""
    lines1 = text1.splitlines()
    lines2 = text2.splitlines()
    diff = difflib.unified_diff(
        lines1, 
        lines2, 
        fromfile="Version 1", 
        tofile="Version 2", 
        lineterm=""
    )
    return "\n".join(diff)

def compare_versions(v1_nodes: List[Any], v2_nodes: List[Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Compares nodes of Version 1 and Version 2 using the Hybrid Matching Strategy:
    1. Exact Heading Path & Hash match
    2. Exact Heading Path match (Modified)
    3. Content Hash match (Moved/Level change)
    4. Fallback Title Similarity match
    5. Added/Deleted Node resolution
    
    Returns:
    - mappings: A list of dicts suitable to populate NodeMapping SQLite objects.
    - summary: A summary dict containing counts of added, deleted, modified, and unchanged nodes.
    """
    logger.info("Starting hybrid version matching comparison...")
    
    v1_by_id = {n.id: n for n in v1_nodes}
    v2_by_id = {n.id: n for n in v2_nodes}
    
    # Calculate paths for all nodes
    v1_paths = {n.id: get_node_path(n.id, v1_by_id) for n in v1_nodes}
    v2_paths = {n.id: get_node_path(n.id, v2_by_id) for n in v2_nodes}
    
    matched_v1: Set[str] = set()
    matched_v2: Set[str] = set()
    
    mappings: List[Dict[str, Any]] = []
    
    # --- Step 1: Heading Path & Hash Match (Exact Match) ---
    logger.debug("Step 1: Heading Path & Hash Match...")
    for n2 in v2_nodes:
        path2 = v2_paths[n2.id]
        # Find exact matches in v1
        for n1 in v1_nodes:
            if n1.id in matched_v1:
                continue
            path1 = v1_paths[n1.id]
            if path1 == path2 and n1.content_hash == n2.content_hash:
                mappings.append({
                    "from_node_id": n1.id,
                    "to_node_id": n2.id,
                    "comparison_status": "unchanged",
                    "diff": None
                })
                matched_v1.add(n1.id)
                matched_v2.add(n2.id)
                break

    # --- Step 2: Heading Path Match (Content Modified) ---
    logger.debug("Step 2: Heading Path Match...")
    for n2 in v2_nodes:
        if n2.id in matched_v2:
            continue
        path2 = v2_paths[n2.id]
        for n1 in v1_nodes:
            if n1.id in matched_v1:
                continue
            path1 = v1_paths[n1.id]
            if path1 == path2:
                diff_text = generate_unified_diff(n1.text, n2.text)
                mappings.append({
                    "from_node_id": n1.id,
                    "to_node_id": n2.id,
                    "comparison_status": "modified",
                    "diff": diff_text
                })
                matched_v1.add(n1.id)
                matched_v2.add(n2.id)
                break

    # --- Step 3: Content Hash Match (Moved sections) ---
    logger.debug("Step 3: Content Hash Match...")
    for n2 in v2_nodes:
        if n2.id in matched_v2:
            continue
        for n1 in v1_nodes:
            if n1.id in matched_v1:
                continue
            if n1.content_hash == n2.content_hash:
                mappings.append({
                    "from_node_id": n1.id,
                    "to_node_id": n2.id,
                    "comparison_status": "unchanged",
                    "diff": None
                })
                matched_v1.add(n1.id)
                matched_v2.add(n2.id)
                break

    # --- Step 4: Fallback Title Similarity Match ---
    logger.debug("Step 4: Fallback Title Similarity Match...")
    similarity_threshold = 0.80
    for n2 in v2_nodes:
        if n2.id in matched_v2:
            continue
        norm_h2 = normalize_heading(n2.heading)
        if not norm_h2:  # Skip empty headings for similarity match to avoid false pairings
            continue
            
        best_match_n1 = None
        best_score = 0.0
        
        for n1 in v1_nodes:
            if n1.id in matched_v1:
                continue
            norm_h1 = normalize_heading(n1.heading)
            if not norm_h1:
                continue
                
            # SequenceMatcher ratio computes similarity between 0 and 1
            score = difflib.SequenceMatcher(None, norm_h1, norm_h2).ratio()
            if score > best_score:
                best_score = score
                best_match_n1 = n1
                
        if best_match_n1 and best_score >= similarity_threshold:
            n1 = best_match_n1
            status = "unchanged" if n1.content_hash == n2.content_hash else "modified"
            diff_text = None if status == "unchanged" else generate_unified_diff(n1.text, n2.text)
            
            mappings.append({
                "from_node_id": n1.id,
                "to_node_id": n2.id,
                "comparison_status": status,
                "diff": diff_text
            })
            matched_v1.add(n1.id)
            matched_v2.add(n2.id)
            logger.debug(f"Matched '{n1.heading}' and '{n2.heading}' by similarity score {best_score:.2f}")

    # --- Step 5: Unmatched nodes (Added / Deleted) ---
    logger.debug("Step 5: Added/Deleted Node resolution...")
    
    # Added nodes in V2
    added_count = 0
    for n2 in v2_nodes:
        if n2.id not in matched_v2:
            # Added: We don't have a V1 node matching this, so it has no from_node_id. 
            # In our NodeMapping model, from_node_id is non-nullable because mapping records connect a node from a base version to a target version.
            # To represent additions and deletions cleanly in the mapping:
            # 1. Any node in V1 that is not matched is a DELETED mapping.
            # 2. Any node in V2 that is not matched is an ADDED node, but since there is no 'from_node_id',
            #    we can represent it in the comparison JSON summary, or we can create a mapping record if we allow null from_node_id.
            # Wait, in the NodeMapping model we wrote earlier:
            # from_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
            # to_node_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=True)
            # So a DELETED node mapping has: from_node_id = n1.id, to_node_id = None, comparison_status = "deleted"
            # How do we record ADDED nodes in NodeMapping if from_node_id is non-nullable?
            # Ah! If a node is ADDED in V2, it does not exist in V1. Since NodeMapping represents transitions FROM a specific version,
            # we don't strictly need a NodeMapping record for an addition, OR we could make from_node_id nullable.
            # Wait! Making from_node_id nullable is a very good design option! Let's check: if from_node_id is nullable, we can have:
            # from_node_id = None, to_node_id = n2.id, comparison_status = "added"
            # But wait, we can also just represent added nodes in the `diff_data` JSON of `VersionComparison`, which stores the full diff summary.
            # The prompt says: "Compare both versions. Detect Added, Deleted, Modified, Unchanged nodes. Store comparison results. Generate lightweight diffs."
            # Storing them in `VersionComparison.diff_data` as a list of added, deleted, modified, unchanged node IDs and metadata is highly flexible and standard.
            # Let's also check if we can represent deletions as NodeMapping records (from_node_id=n1.id, to_node_id=None, status="deleted"). Yes, that works perfectly.
            # Let's make sure we track added nodes in the `VersionComparison` diff_data!
            added_count += 1
            
    deleted_count = 0
    # Deleted nodes in V1
    for n1 in v1_nodes:
        if n1.id not in matched_v1:
            mappings.append({
                "from_node_id": n1.id,
                "to_node_id": None,
                "comparison_status": "deleted",
                "diff": None
            })
            matched_v1.add(n1.id)
            deleted_count += 1
            
    # Compile comparison summary
    unchanged_count = sum(1 for m in mappings if m["comparison_status"] == "unchanged")
    modified_count = sum(1 for m in mappings if m["comparison_status"] == "modified")
    
    summary = {
        "added_count": added_count,
        "deleted_count": deleted_count,
        "modified_count": modified_count,
        "unchanged_count": unchanged_count,
        "total_v1": len(v1_nodes),
        "total_v2": len(v2_nodes)
    }
    
    logger.info(f"Comparison finished: {added_count} Added, {deleted_count} Deleted, {modified_count} Modified, {unchanged_count} Unchanged.")
    return mappings, summary
