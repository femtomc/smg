# semg

Semantic graph for software architecture — built for agents and humans.

`semg` turns your codebase into a queryable graph of modules, classes, functions, and their relationships. Agents use it to understand architecture before writing code. Humans use it to generate diagrams and explore dependencies.

## Install

```bash
# As a global CLI tool (recommended, all languages)
uv tool install semg \
  --from git+https://github.com/femtomc/semg \
  --with tree-sitter \
  --with tree-sitter-python \
  --with tree-sitter-javascript \
  --with tree-sitter-typescript \
  --with tree-sitter-zig \
  --with watchdog

# Minimal (Python only)
uv tool install semg --from git+https://github.com/femtomc/semg --with tree-sitter --with tree-sitter-python
```

## Quick start

```bash
cd your-project
semg init
semg scan src/

# Ask questions
semg about MyClass           # What is this?
semg impact MyClass          # What breaks if I change it?
semg between api.routes db   # How do these relate?
semg overview                # Orient me
semg diff                    # What changed since last commit?
```

## Supported languages

| Language | Extensions | Grammar |
|----------|-----------|---------|
| Python | `.py` | `tree-sitter-python` |
| JavaScript | `.js`, `.jsx`, `.mjs`, `.cjs` | `tree-sitter-javascript` |
| TypeScript | `.ts`, `.tsx` | `tree-sitter-typescript` |
| Zig | `.zig` | `tree-sitter-zig` |

All languages extract: classes/structs, functions, methods, constants, containment, imports, inheritance, call graph, and per-function metrics. Adding a new language means writing a `langs/<language>.py` extractor + a `BranchMap` — the metrics engine and scanner are shared.

## How it works

`semg` stores a graph of code entities in `.semg/graph.jsonl` at your project root. Each line is a node (module, class, function, ...) or a typed edge (contains, calls, imports, inherits, ...).

There are three ways to populate the graph:

1. **`semg scan`** — tree-sitter parses source files and extracts symbols, containment, imports, inheritance, and call graph automatically.
2. **Manual CLI** — agents or humans add nodes and edges directly with `semg add` and `semg link`.
3. **Both** — scan for the baseline, then layer on domain-specific relationships (e.g. "tests", "endpoint", custom types).

### Provenance tracking

Every node and edge is tagged with `source: "scan"` or `source: "manual"`. When rescanning, only scan-sourced nodes are cleaned — manual annotations survive. If a rescan deletes a node that had manual edges, those orphaned edges are reported so the agent can re-link them.

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
semg diff                        # What changed structurally since last commit?
semg query deps auth.service     # What does this depend on? (forward transitive)
```

### 3. Inspect

```bash
semg show auth.service           # Node details + direct edges + metrics
semg query outgoing auth.service --rel calls  # What does it call?
semg query incoming auth.service --rel calls  # What calls it?
semg list --type class           # All classes in the graph
```

### 4. Mutate

```bash
semg add endpoint /api/login --doc "Login endpoint" --meta method=POST
semg link api.routes calls auth.service
semg scan src/ --clean           # Full rescan (smart clean preserves manual edges)
semg scan --changed              # Incremental: only rescan files changed since HEAD
semg scan --since HEAD~3         # Incremental: since a specific ref
semg watch src/                  # Auto-rescan on file changes (background)
```

### 5. Batch operations

```bash
echo '{"op":"add","type":"module","name":"app"}
{"op":"add","type":"function","name":"app.main"}
{"op":"link","source":"app","rel":"contains","target":"app.main"}' | semg batch
```

One graph load/save cycle for all mutations. Partial failure tolerant — errors on individual lines are reported but don't stop processing.

### 6. Export

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
| `semg diff [REF]` | Structural diff against a git ref (default: HEAD) |

### Inspect

| Command | Purpose |
|---------|---------|
| `semg show <name>` | Node details + connections + metrics |
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
| `semg scan --changed` | Incremental: rescan files changed since HEAD |
| `semg scan --since REF` | Incremental: rescan files changed since a git ref |
| `semg watch [PATH...]` | Auto-rescan on file changes (Ctrl+C to stop) |
| `semg add <type> <name> [--file --line --doc --meta K=V]` | Add/upsert a node |
| `semg link <source> <rel> <target>` | Add an edge |
| `semg rm <name>` | Remove a node + all its edges |
| `semg unlink <source> <rel> <target>` | Remove an edge |
| `semg update <name> [--type --file --line --doc --meta K=V]` | Update node fields |
| `semg batch` | JSONL commands from stdin, one load/save cycle |

### Export

| Command | Purpose |
|---------|---------|
| `semg export json [--indent]` | Full graph as JSON |
| `semg export mermaid` | Mermaid flowchart |
| `semg export dot` | Graphviz DOT |
| `semg export text` | Human-readable listing |

## Metrics

Every function and method node includes AST-based metrics in its metadata, computed automatically during scan:

| Metric | Description |
|--------|-------------|
| `cyclomatic_complexity` | 1 + branches + boolean operators |
| `cognitive_complexity` | Branches weighted by nesting depth (Sonar-style) |
| `max_nesting_depth` | Deepest control flow nesting |
| `lines_of_code` | Function body line count |
| `parameter_count` | Number of parameters |
| `return_count` | Number of return statements |
| `fan_in` | How many functions call this one |
| `fan_out` | How many functions this one calls |

Language-agnostic — metrics are computed from tree-sitter ASTs using a per-language `BranchMap` that maps node types to semantic roles.

```bash
# Top 5 most complex functions
semg list --type function --format json | python3 -c "
import sys, json
for n in sorted(json.load(sys.stdin),
    key=lambda x: x.get('metadata',{}).get('metrics',{}).get('cyclomatic_complexity',0),
    reverse=True)[:5]:
    m = n['metadata']['metrics']
    print(f'{m[\"cyclomatic_complexity\"]:3d} CC  {n[\"name\"]}')"
```

## Node types

`package`, `module`, `class`, `function`, `method`, `interface`, `variable`, `constant`, `type`, `endpoint`, `config` — plus any custom string.

## Relationship types

`calls`, `inherits`, `implements`, `contains`, `depends_on`, `imports`, `returns`, `accepts`, `overrides`, `decorates`, `tests` — plus any custom string.

## Data format

`.semg/graph.jsonl` — one JSON object per line:

```jsonl
{"kind":"node","name":"app.core.Engine","type":"class","file":"src/app/core.py","line":12,"docstring":"The engine.","metadata":{"source":"scan","metrics":{...}}}
{"kind":"edge","source":"app.core","rel":"contains","target":"app.core.Engine","metadata":{"source":"scan"}}
```

Git-friendly, human-readable, parseable with zero tooling. Nodes sorted by name, edges by (source, rel, target). Written atomically via temp file + rename.

## Name resolution

Node names are fully qualified (`app.core.Engine.run`), but you can use short names:

```bash
semg about Engine          # Matches app.core.Engine if unambiguous
semg show run              # Error if multiple matches — lists candidates
```

## Design principles

- **Agent-first**: JSON by default when piped, structured output, exit codes for branching
- **Gradual disclosure**: `about` → `show` → `query` — start simple, drill down as needed
- **Language-agnostic**: tree-sitter grammars for any language, BranchMap protocol for metrics
- **Incremental**: `--changed` rescans only modified files, `watch` for live updates
- **Provenance-aware**: scan vs manual annotations tracked, manual edges survive rescans
- **Zero config**: `semg init && semg scan .` works on any supported project
- **Git-friendly**: JSONL is diffable, sorted deterministically, written atomically

## License

MIT
