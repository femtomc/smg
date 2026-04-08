"""Search cache schema and identifier splitting."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS nodes (
    node_id      INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    name_tokens  TEXT NOT NULL,
    kind         TEXT NOT NULL,
    file         TEXT,
    line_start   INTEGER,
    line_end     INTEGER,
    docstring    TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    name_tokens,
    docstring,
    content='nodes',
    content_rowid='node_id',
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
  INSERT INTO nodes_fts(rowid, name_tokens, docstring)
  VALUES (new.node_id, new.name_tokens, new.docstring);
END;

CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
  INSERT INTO nodes_fts(nodes_fts, rowid, name_tokens, docstring)
  VALUES ('delete', old.node_id, old.name_tokens, old.docstring);
END;

CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
  INSERT INTO nodes_fts(nodes_fts, rowid, name_tokens, docstring)
  VALUES ('delete', old.node_id, old.name_tokens, old.docstring);
  INSERT INTO nodes_fts(rowid, name_tokens, docstring)
  VALUES (new.node_id, new.name_tokens, new.docstring);
END;

CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);

CREATE TABLE IF NOT EXISTS search_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
INSERT OR REPLACE INTO search_meta(key, value) VALUES
    ('schema_version', '1'),
    ('tokenizer_version', '1');
"""

SEARCH_DB_NAME = "search.sqlite3"
SCHEMA_VERSION = "1"


def split_identifier(name: str) -> str:
    """Split a dotted/camelCase identifier into space-separated tokens.

    >>> split_identifier("smg.cli.helpers._truncate")
    'smg cli helpers truncate'
    >>> split_identifier("parseHTMLDocument")
    'parse html document'
    >>> split_identifier("smg.graph.SemGraph.analyze_hot")
    'smg graph sem graph analyze hot'
    """
    # dots and underscores to spaces
    s = re.sub(r"[._]+", " ", name)
    # CamelCase: insert space before a capital that follows a lowercase/digit
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    # CamelCase: insert space between adjacent capitals when followed by lowercase
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    # fold, collapse whitespace
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def search_db_path(root: Path) -> Path:
    """Return the path to .smg/search.sqlite3."""
    return root / ".smg" / SEARCH_DB_NAME


def create_search_db(db_path: Path) -> sqlite3.Connection:
    """Create (or open) the search database and ensure schema exists."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    return conn


def check_schema_version(conn: sqlite3.Connection) -> bool:
    """Return True if the db schema version matches the current code."""
    try:
        row = conn.execute("SELECT value FROM search_meta WHERE key = 'schema_version'").fetchone()
        return row is not None and row[0] == SCHEMA_VERSION
    except sqlite3.OperationalError:
        return False
