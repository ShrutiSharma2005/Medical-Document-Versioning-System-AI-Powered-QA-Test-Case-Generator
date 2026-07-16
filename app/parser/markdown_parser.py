import hashlib
import re
import uuid
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional
from loguru import logger

def clean_heading_text(raw_text: str) -> str:
    """Strips markdown bold markers and leading/trailing whitespace from heading text."""
    # Remove markdown bold/italic asterisks
    cleaned = raw_text.replace("**", "").replace("*", "").replace("`", "").strip()
    return cleaned

def parse_markdown_to_nodes(markdown_content: str, version_id: str) -> List[Dict[str, Any]]:
    """
    Parses a markdown string into a hierarchical document tree.
    Returns a list of dict representation of Node objects ready to be persisted.
    
    Each node contains:
    - id (UUID)
    - version_id (UUID)
    - parent_id (UUID or None)
    - heading (string)
    - level (int, 1-6)
    - text (string)
    - content_hash (string)
    - sort_order (int)
    - created_at (datetime)
    """
    logger.info(f"Parsing markdown document for version {version_id}...")
    lines = markdown_content.splitlines()
    nodes = []
    
    # Parent stack holds dicts with "level" and "id"
    stack: List[Dict[str, Any]] = []
    
    # Virtual intro node for any lines appearing before the first heading
    intro_node_id = str(uuid.uuid4())
    intro_node = {
        "id": intro_node_id,
        "version_id": version_id,
        "parent_id": None,
        "heading": "Intro",
        "level": 1,
        "text_lines": [],
        "sort_order": 0,
        "created_at": datetime.now(UTC)
    }
    
    current_node = intro_node
    sort_counter = 0
    first_heading_seen = False
    
    for line_num, line in enumerate(lines, 1):
        # Match markdown headings (1 to 6 hash marks followed by space or end of line)
        heading_match = re.match(r'^(#{1,6})(?:\s+(.*)|$)', line)
        if heading_match:
            level = len(heading_match.group(1))
            raw_title = heading_match.group(2) or ""
            title = clean_heading_text(raw_title)
            
            logger.debug(f"Line {line_num}: Found heading level {level} - '{title}'")
            
            # If this is the first heading we see, check if the intro node contains any text
            if not first_heading_seen:
                first_heading_seen = True
                if any(t.strip() for t in intro_node["text_lines"]):
                    nodes.append(intro_node)
                    sort_counter += 1
                    logger.debug(f"Added virtual Intro node for text prior to first heading.")
            
            new_node_id = str(uuid.uuid4())
            
            # Adjust hierarchy stack: pop nodes until we find a parent with level < current heading level
            while stack and stack[-1]["level"] >= level:
                stack.pop()
                
            parent_id = stack[-1]["id"] if stack else None
            
            new_node = {
                "id": new_node_id,
                "version_id": version_id,
                "parent_id": parent_id,
                "heading": title,
                "level": level,
                "text_lines": [],
                "sort_order": sort_counter,
                "created_at": datetime.now(UTC)
            }
            sort_counter += 1
            
            nodes.append(new_node)
            current_node = new_node
            stack.append({"level": level, "id": new_node_id})
        else:
            # Regular text line (body, table, list, code block etc.), append to current active node
            current_node["text_lines"].append(line)
            
    # Append the intro node if we never encountered a heading but there was content
    if not first_heading_seen and any(t.strip() for t in intro_node["text_lines"]) and intro_node not in nodes:
        nodes.append(intro_node)
        logger.debug("Document contains no headings. Created virtual Intro node.")
        
    # Post-process to compute text blocks and SHA-256 hashes
    for node in nodes:
        # Join lines exactly as they are to avoid losing content, and strip edge whitespaces
        body_text = "\n".join(node["text_lines"]).strip()
        node["text"] = body_text
        del node["text_lines"]
        
        # Calculate unique content hash
        hash_input = f"{node['heading']}\n{node['text']}"
        node["content_hash"] = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        
        logger.debug(f"Parsed node '{node['heading']}' with level {node['level']} and hash {node['content_hash'][:8]}...")
        
    logger.info(f"Successfully parsed {len(nodes)} nodes from markdown.")
    return nodes
