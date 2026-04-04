"""Structural and content hashing for tree-sitter AST nodes.

Uses xxHash64 for speed — ~10x faster than SHA-256, and we don't need
cryptographic strength (these hashes are for matching within a single diff).
"""
from __future__ import annotations

import xxhash
from tree_sitter import Node as TSNode

# Nodes to skip entirely — they don't affect structure
_SKIP = frozenset({
    "comment", "line_comment", "block_comment",
})

# Nodes to normalize — replace with positional placeholder
_NORMALIZE = frozenset({
    "identifier", "type_identifier", "field_identifier",
    "string", "string_content", "string_literal",
    "integer", "integer_literal", "float", "float_literal",
    "number", "true", "false", "none", "null",
})


def content_hash(source: bytes, start_byte: int, end_byte: int) -> str:
    """xxHash64 of the exact source bytes for a node's range, as 16 hex chars."""
    return xxhash.xxh64(source[start_byte:end_byte]).hexdigest()


def structure_hash(node: TSNode) -> str:
    """xxHash64 of the normalized AST structure.

    Walks the tree depth-first. Comment nodes are skipped entirely.
    Identifier and literal nodes are replaced with a placeholder.
    All other nodes contribute their type to the hash.
    """
    h = xxhash.xxh64()
    _walk(node, h)
    return h.hexdigest()


def _walk(node: TSNode, h: xxhash.xxh64) -> None:
    """Iterative DFS hash walk with structure markers."""
    stack: list[TSNode | None] = [node]
    while stack:
        n = stack.pop()
        if n is None:
            h.update(b")")
            continue
        if n.type in _SKIP:
            continue
        if n.type in _NORMALIZE:
            h.update(b"_")
            continue
        h.update(n.type.encode())
        h.update(b"(")
        # Push end marker, then children in reverse for left-to-right processing
        stack.append(None)
        for i in range(n.child_count - 1, -1, -1):
            child = n.children[i]
            if child.type not in _SKIP:
                stack.append(child)
