"""SMG fuzzy search cache — SQLite+FTS5 over the code graph."""

from __future__ import annotations

from smg.search.indexer import rebuild_search_index
from smg.search.query import normalize_query, search_nodes
from smg.search.schema import split_identifier

__all__ = [
    "rebuild_search_index",
    "normalize_query",
    "search_nodes",
    "split_identifier",
]
