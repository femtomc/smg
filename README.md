# semg

Semantic graph for software architecture — built for agents and humans.

`semg` turns your codebase into a queryable graph of modules, classes, functions, and their relationships. Agents use it to understand architecture before writing code. Humans use it to generate diagrams and explore dependencies.

## Install

```bash
# As a global CLI tool (recommended)
uv tool install semg --from git+https://github.com/femtomc/semg --with tree-sitter --with tree-sitter-python

# Or in a project
uv add semg
uv add --optional scan tree-sitter tree-sitter-python
```

## Quick start

```bash
# Initialize in any project
cd your-project
semg init

# Auto-populate from source (requires tree-sitter)
semg scan src/

# Ask questions
semg about MyClass           # What is this?
semg impact MyClass          # What breaks if I change it?
semg between api.routes db   # How do these relate?
semg overview                # Orient me
```

## How it works

`semg` stores a graph of code entities in `.semg/graph.jsonl` at your project root. Each line is a node (module, class, function, ...) or a typed edge (contains, calls, imports, inherits, ...).

There are three ways to populate the graph:

1. **`semg scan`** — tree-sitter parses your source files and extracts symbols, containment, imports, and inheritance automatically.
2. **Manual CLI** — agents or humans add nodes and edges directly with `semg add` and `semg link`.
3. **Both** — scan for the baseline, then layer on domain-specific relationships (e.g. "tests", "endpoint", custom types).

### Auto-format detection

When stdout is a **terminal**, output is rich text with colors and tables. When stdout is **piped** (i.e. an agent is reading it), output is automatically JSON. No flags needed.

```bash
# Human sees a rich panel
semg about SemGraph

# Agent gets structured JSON
result=$(semg about SemGraph)
```

You can always override with `--format text` or `--format json`.

## Agent usage

Agents should treat `semg` as a codebase database. The typical workflow:

### 1. Orient

```bash
semg overview                    # Graph stats, top connected nodes, module sizes
semg about auth.service          # Context card: type, file, connections, containment path
```

### 2. Investigate

```bash
semg impact auth.service         # What depends on this? (reverse transitive)
semg between api.routes db.models  # How do these connect?
semg query deps auth.service     # What does this depend on? (forward transitive)
```

### 3. Inspect

```bash
semg show auth.service           # Node details + direct edges
semg query outgoing auth.service --rel calls  # What does it call?
semg query incoming auth.service --rel calls  # What calls it?
semg list --type class           # All classes in the graph
```

### 4. Mutate

```bash
semg add endpoint /api/login --doc "Login endpoint" --meta method=POST
semg link api.routes calls auth.service
semg scan src/ --clean           # Re-scan after code changes
```

### 5. Export

```bash
semg export mermaid              # Paste into docs
semg export dot | dot -Tpng -o graph.png  # Render with Graphviz
semg export json --indent        # Full graph as JSON
```

## Commands

### Explore (start here)

| Command | Purpose |
|---------|---------|
| `semg about <name> [--depth 0\|1\|2]` | Progressive context card |
| `semg impact <name> [--depth N]` | Reverse transitive impact analysis |
| `semg between <A> <B>` | Shortest path + direct edges |
| `semg overview [--top N]` | Graph stats + most connected nodes |

### Inspect

| Command | Purpose |
|---------|---------|
| `semg show <name>` | Node details + connections |
| `semg list [--type TYPE]` | List nodes |
| `semg status` | Node/edge count breakdown |
| `semg query deps <name>` | Transitive dependencies |
| `semg query callers <name>` | What calls this? |
| `semg query path <A> <B>` | Shortest path |
| `semg query subgraph <name> [--depth N]` | N-hop neighborhood |
| `semg query incoming <name> [--rel TYPE]` | Incoming edges |
| `semg query outgoing <name> [--rel TYPE]` | Outgoing edges |
| `semg validate` | Check graph integrity |

### Mutate

| Command | Purpose |
|---------|---------|
| `semg init` | Create `.semg/` in current directory |
| `semg scan [PATH...] [--clean]` | Auto-populate from source via tree-sitter |
| `semg add <type> <name> [--file --line --doc --meta K=V]` | Add/upsert a node |
| `semg link <source> <rel> <target>` | Add an edge |
| `semg rm <name>` | Remove a node + all its edges |
| `semg unlink <source> <rel> <target>` | Remove an edge |
| `semg update <name> [--type --file --line --doc --meta K=V]` | Update node fields |

### Export

| Command | Purpose |
|---------|---------|
| `semg export json [--indent]` | Full graph as JSON |
| `semg export mermaid` | Mermaid flowchart |
| `semg export dot` | Graphviz DOT |
| `semg export text` | Human-readable listing |

## Node types

`package`, `module`, `class`, `function`, `method`, `interface`, `variable`, `constant`, `type`, `endpoint`, `config` — plus any custom string.

## Relationship types

`calls`, `inherits`, `implements`, `contains`, `depends_on`, `imports`, `returns`, `accepts`, `overrides`, `decorates`, `tests` — plus any custom string.

## Data format

`.semg/graph.jsonl` — one JSON object per line:

```jsonl
{"kind":"node","name":"app.core.Engine","type":"class","file":"src/app/core.py","line":12,"docstring":"The engine."}
{"kind":"edge","source":"app.core","rel":"contains","target":"app.core.Engine"}
{"kind":"edge","source":"app.core.Engine","rel":"inherits","target":"app.core.Base"}
```

Git-friendly, human-readable, parseable with zero tooling. Nodes are sorted by name, edges by (source, rel, target).

## Tree-sitter scan

`semg scan` uses [tree-sitter](https://tree-sitter.github.io/) to parse source files. Currently supports Python. Adding a new language means writing a `langs/<language>.py` extractor with tree-sitter queries — the framework handles file walking, name resolution, and graph population.

What scan extracts from Python:

- **Nodes**: packages, modules, classes, functions, methods, constants (UPPERCASE assignments)
- **Edges**: containment (from AST nesting), imports, inheritance, decorators
- **Metadata**: docstrings, file paths, line numbers

```bash
# Install with scan support
uv tool install semg --from git+https://github.com/femtomc/semg --with tree-sitter --with tree-sitter-python

# Scan and query
semg init && semg scan src/
semg overview
```

## Name resolution

Node names are fully qualified (`app.core.Engine.run`), but you can use short names:

```bash
semg about Engine          # Matches app.core.Engine if unambiguous
semg show run              # Error if multiple matches — lists candidates
```

## Design principles

- **Agent-first**: JSON by default when piped, structured output, exit codes for branching
- **Gradual disclosure**: `about` → `show` → `query` — start simple, drill down as needed
- **Language-agnostic**: tree-sitter grammars for any language, manual entry as escape hatch
- **Zero config**: `semg init && semg scan .` works on any Python project
- **Git-friendly**: JSONL is diffable, sorted deterministically, written atomically

## License

MIT
