"""Rebuild the search index from a SemGraph."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from smg.search.schema import (
    check_schema_version,
    create_search_db,
    search_db_path,
    split_identifier,
)

if TYPE_CHECKING:
    from smg.graph import SemGraph


def rebuild_search_index(graph: SemGraph, root: Path) -> None:
    """Rebuild .smg/search.sqlite3 from *graph* in a single transaction.

    Drops and repopulates the nodes table; triggers keep FTS in sync.
    """
    db_path = search_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # If schema is stale, recreate from scratch
    if db_path.exists():
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        if not check_schema_version(conn):
            conn.close()
            db_path.unlink()

    conn = create_search_db(db_path)
    try:
        with conn:
            # Clear existing data
            conn.execute("DELETE FROM nodes")

            # Insert all graph nodes
            rows = []
            for i, node in enumerate(graph.all_nodes(), 1):
                name_tokens = split_identifier(node.name)
                doc = node.docstring or ""
                rows.append(
                    (
                        i,
                        node.name,
                        name_tokens,
                        node.type.value,
                        node.file,
                        node.line,
                        node.end_line,
                        doc,
                    )
                )

            conn.executemany(
                "INSERT INTO nodes (node_id, name, name_tokens, kind, file, "
                "line_start, line_end, docstring) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
    finally:
        conn.close()
