# smg

`smg` turns a codebase into a queryable graph of modules, classes, functions, and their relationships. Agents use it to understand architecture before writing code. Humans use it to generate diagrams and explore dependencies.

## Install

```bash
# All languages
uv tool install smg \
  --from git+https://github.com/femtomc/smg \
  --with tree-sitter \
  --with tree-sitter-python \
  --with tree-sitter-javascript \
  --with tree-sitter-typescript \
  --with tree-sitter-c \
  --with tree-sitter-zig \
  --with xxhash \
  --with watchdog

# Python only
uv tool install smg --from git+https://github.com/femtomc/smg --with tree-sitter --with tree-sitter-python --with xxhash
```

## Quick start

```bash
cd your-project
smg init
smg scan src/

# Ask questions
smg about MyClass           # What is this?
smg usages MyClass          # Where is it used?
smg impact MyClass          # What breaks if I change it?
smg between api.routes db   # How do these relate?
smg overview                # Orient me

# Analyze
smg analyze                 # Architectural analysis with hotspot detection
smg diff                    # What changed? (with rename/move detection)
smg blame MyClass           # Who last touched this?
smg context MyClass --tokens 8000  # Pack source for an LLM prompt

# Enforce
smg rule add acyclic --invariant no-cycles
smg check                   # Enforce architectural rules
```

## Supported languages

| Language | Extensions | Grammar |
|----------|-----------|---------|
| Python | `.py` | `tree-sitter-python` |
| JavaScript | `.js`, `.jsx`, `.mjs`, `.cjs` | `tree-sitter-javascript` |
| TypeScript | `.ts`, `.tsx` | `tree-sitter-typescript` |
| C/C++ | `.c`, `.h`, `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`, `.hxx` | `tree-sitter-c` |
| CUDA | `.cu`, `.cuh` | `tree-sitter-c` (C++ parser) |
| Metal | `.metal` | `tree-sitter-cpp` |
| Zig | `.zig` | `tree-sitter-zig` |

All languages extract: classes/structs, functions, methods, constants, containment, imports, inheritance, call graph, and per-function metrics. Adding a language means writing a `langs/<language>.py` extractor and a `BranchMap` -- the metrics engine and scanner are shared.

## How it works

`smg` stores a graph of code entities in `.smg/graph.jsonl` at your project root. Each line is a node (module, class, function, ...) or a typed edge (contains, calls, imports, inherits, ...).

There are three ways to populate the graph:

1. **`smg scan`** -- tree-sitter parses source files and extracts symbols, containment, imports, inheritance, and call graph automatically.
2. **Manual CLI** -- agents or humans add nodes and edges directly with `smg add` and `smg link`.
3. **Both** -- scan for the baseline, then layer on domain-specific relationships (e.g. "tests", "endpoint", custom types).

### Structural hashing

During extraction, every function, method, and class gets two hashes stored in its metadata:

- **Content hash** -- xxHash64 of the entity's raw source bytes. If two entities have the same content hash, their source code is identical.
- **Structure hash** -- xxHash64 of a normalized AST walk that skips comments, identifiers, and literals but preserves node types and nesting. If two entities have the same structure hash, they have the same control flow shape even if variable names, strings, or comments differ.

These hashes power rename/move detection in `smg diff` (see below). They are computed automatically during scan and persisted in the graph.

### Provenance tracking

Every node and edge is tagged with `source: "scan"` or `source: "manual"`. When rescanning, only scan-sourced nodes are cleaned -- manual annotations survive. If a rescan deletes a node that had manual edges, those orphaned edges are reported so the agent can re-link them.

### Excluding files

`smg scan` skips common non-source directories by default (`.git`, `node_modules`, `__pycache__`, `.venv`, etc.). You can extend this in two ways:

- **`--exclude` flag** -- pass additional glob patterns per invocation: `smg scan src/ --exclude "*.generated.py" --exclude "vendor/*"`
- **`.smgignore` file** -- place a `.smgignore` at your project root with one glob pattern per line (same syntax as `.gitignore`). These patterns are loaded automatically on every scan.

### Auto-format detection

When stdout is a **terminal**, output is rich text with colors and tables. When stdout is **piped** (i.e. an agent is reading it), output is JSON. No flags needed.

```bash
# Human sees a rich panel
smg about auth.service

# Agent gets structured JSON
result=$(smg about auth.service)
```

You can always override with `--format text` or `--format json`.

## Agent usage

Agents should treat `smg` as a codebase database. The typical workflow:

### 1. Orient

```bash
smg overview                    # Graph stats, top connected nodes, module sizes
smg about auth.service          # Context card: type, file, connections, containment path
```

### 2. Investigate

```bash
smg usages auth.service         # Who uses this? (all direct references)
smg impact auth.service         # What depends on this? (reverse transitive)
smg between api.routes db.models  # How do these connect?
smg diff                        # What changed structurally since last commit?
smg blame auth.service          # Who last touched this and when?
smg analyze                     # Cycles, dead code, hotspots, code smells, churn
smg analyze --summary --top 5   # Key findings only
smg query deps auth.service     # What does this depend on? (forward transitive)
```

### 3. Build context

When preparing a prompt for an LLM, `smg context` packs relevant source code into a token budget:

```bash
smg context auth.service --tokens 8000
```

This walks outward from the target entity in the dependency graph and greedily includes source code, prioritizing by proximity:

1. **Target entity** -- full source (always included)
2. **Direct dependencies and dependents** (1-hop) -- full source, downgraded to signature if over budget
3. **2-hop neighbors** -- signature only (just the function/class declaration)
4. **3-hop neighbors** -- summary only (name, type, file location, docstring)

If the budget fills up at any tier, remaining entries are downgraded to the next level. Output is structured JSON when piped, syntax-highlighted source when in terminal. The token counter defaults to `len(text) / 4` (~4 chars per token) but is pluggable via the library API.

### 4. Enforce

```bash
smg rule add layering --deny "infra.* -> app.*"
smg rule add acyclic --invariant no-cycles
smg rule add reachable --invariant no-dead-code --entry-points "main,cli.*"
smg check                       # check all rules (exit 1 on violation)
smg check layering              # check a specific rule
```

### 5. Inspect

```bash
smg show auth.service           # Node details + direct edges + metrics
smg query outgoing auth.service --rel calls  # What does it call?
smg query incoming auth.service --rel calls  # What calls it?
smg list --type class           # All classes in the graph
```

### 6. Mutate

```bash
smg add endpoint /api/login --doc "Login endpoint" --meta method=POST
smg link api.routes calls auth.service
smg scan src/ --clean           # Rescan (smart clean preserves manual edges)
smg scan --changed              # Incremental: only files changed since HEAD
smg scan --since HEAD~3         # Incremental: since a specific ref
smg watch src/                  # Auto-rescan on file changes (background)
```

### 7. Batch operations

```bash
echo '{"op":"add","type":"module","name":"app"}
{"op":"add","type":"function","name":"app.main"}
{"op":"link","source":"app","rel":"contains","target":"app.main"}' | smg batch
```

One graph load/save cycle for all mutations. Partial failure tolerant -- errors on individual lines are reported but don't stop processing.

### 8. Export

```bash
smg export mermaid              # Paste into docs
smg export dot | dot -Tpng -o graph.png  # Render with Graphviz
smg export json --indent        # Full graph as JSON
```

## Commands

### Explore

| Command | Purpose |
|---------|---------|
| `smg about <name> [--depth 0\|1\|2]` | Context card with progressive detail |
| `smg usages <name>` | Where is X used? All direct references with source location |
| `smg impact <name> [--depth N]` | Reverse transitive impact analysis |
| `smg between <A> <B>` | Shortest path + direct edges |
| `smg overview [--top N]` | Graph stats + most connected nodes |
| `smg diff [REF]` | Structural diff with rename/move detection (default: HEAD) |
| `smg analyze [--top N] [--module PREFIX] [--summary] [--churn-days N]` | Architectural analysis (see below) |
| `smg context <name> [--tokens N]` | Pack source code for LLM context within a token budget |
| `smg blame <name\|file>` | Entity-level git blame: who last touched this? |

### Enforce

| Command | Purpose |
|---------|---------|
| `smg rule add <name> --deny "PATTERN"` | Forbid edges matching a glob pattern |
| `smg rule add <name> --invariant TYPE` | Require a structural invariant (see below) |
| `smg rule list` | List all rules |
| `smg rule rm <name>` | Remove a rule |
| `smg check [NAME]` | Check all rules (or one). Exit 1 on violation. |

### Inspect

| Command | Purpose |
|---------|---------|
| `smg show <name>` | Node details + connections + metrics |
| `smg list [--type TYPE]` | List nodes |
| `smg status` | Node/edge count breakdown |
| `smg query deps <name>` | Transitive dependencies |
| `smg query callers <name>` | What calls this? |
| `smg query path <A> <B>` | Shortest path |
| `smg query subgraph <name> [--depth N]` | N-hop neighborhood |
| `smg query incoming <name> [--rel TYPE]` | Incoming edges |
| `smg query outgoing <name> [--rel TYPE]` | Outgoing edges |
| `smg validate` | Check graph integrity |

### Mutate

| Command | Purpose |
|---------|---------|
| `smg init` | Create `.smg/` in current directory |
| `smg scan [PATH...] [--clean] [--exclude GLOB]` | Auto-populate from source via tree-sitter |
| `smg scan --changed` | Incremental: rescan files changed since HEAD |
| `smg scan --since REF` | Incremental: rescan files changed since a git ref |
| `smg watch [PATH...]` | Auto-rescan on file changes (Ctrl+C to stop) |
| `smg add <type> <name> [--file --line --doc --meta K=V]` | Add/upsert a node |
| `smg link <source> <rel> <target>` | Add an edge |
| `smg rm <name>` | Remove a node + all its edges |
| `smg unlink <source> <rel> <target>` | Remove an edge |
| `smg update <name> [--type --file --line --doc --meta K=V]` | Update node fields |
| `smg batch` | JSONL commands from stdin, one load/save cycle |

### Export

| Command | Purpose |
|---------|---------|
| `smg export json [--indent]` | Full graph as JSON |
| `smg export mermaid` | Mermaid flowchart |
| `smg export dot` | Graphviz DOT |
| `smg export text` | Human-readable listing |

## Structural diff

`smg diff` compares the current graph against a git ref and reports structural changes: added, removed, changed, and **renamed/moved** nodes and edges.

```bash
smg diff              # vs HEAD (last commit)
smg diff HEAD~3       # vs 3 commits ago
smg diff main         # vs another branch
```

Rename and move detection uses a three-phase matching algorithm on unmatched added/removed nodes:

1. **Content hash match** -- if a removed node and an added node have identical source bytes (same content hash), the entity was purely renamed or moved with no code changes. Reported as an "exact" match.
2. **Structure hash match** -- if there's a unique structural match (same AST shape but different content, e.g. a variable was renamed inside the function), the entity was renamed with minor edits. Reported as a "structural" match.
3. **Fuzzy name similarity** -- for still-unmatched entities of the same type, smg computes [Jaccard similarity][jaccard] on whitespace-split tokens of their fully-qualified names. Pairs above 0.8 similarity are classified as renamed/moved. This catches cases where both the entity's name and its body changed significantly but the name tokens mostly overlap (e.g. `app.utils.parse_config` → `app.helpers.parse_config`).

Anything unmatched after all three phases is reported as a plain addition or deletion.

## Entity-level blame

`smg blame` maps graph entities to the most recent git commit that touched their source lines:

```bash
# Single entity
smg blame SemGraph
# smg.graph.SemGraph [class]
#   src/smg/graph.py:14-251
#   69a55085a058 user@email.com (2024-01-15)
#   Optimize scan and analysis hot paths

# All entities in a file
smg blame src/smg/graph.py
```

For a single entity, it runs `git log -1 -L <start>,<end>:<file>` to find the commit that last modified the entity's line range. For a file, it blames every entity in that file and displays a table sorted by line number. Output is JSON when piped.

## Per-function metrics

Every function and method node includes AST-based metrics in its metadata, computed automatically during scan:

| Metric | Description |
|--------|-------------|
| `cyclomatic_complexity` | Number of linearly independent paths through a function. 1 + branches + boolean operators. [McCabe (1976)][mccabe] |
| `cognitive_complexity` | Branches weighted by nesting depth -- penalizes deeply nested logic more than flat branching. [Campbell (2018)][cognitive] |
| `max_nesting_depth` | Deepest control flow nesting level |
| `lines_of_code` | Function body line count |
| `parameter_count` | Number of parameters |
| `return_count` | Number of return statements |
| `fan_in` | How many functions call this one |
| `fan_out` | How many functions this one calls |

Language-agnostic -- metrics are computed from tree-sitter ASTs using a per-language `BranchMap` that maps node types to semantic roles.

```bash
# Top 5 most complex functions
smg list --type function --format json | python3 -c "
import sys, json
for n in sorted(json.load(sys.stdin),
    key=lambda x: x.get('metadata',{}).get('metrics',{}).get('cyclomatic_complexity',0),
    reverse=True)[:5]:
    m = n['metadata']['metrics']
    print(f'{m[\"cyclomatic_complexity\"]:3d} CC  {n[\"name\"]}')"
```

## Architectural analysis

`smg analyze` runs graph-theoretic, OO, smell-detection, and git-churn analyses in a single pass.

```bash
smg analyze                        # all analyses
smg analyze --module auth          # scope to auth.* nodes
smg analyze --since HEAD~5         # only analyze changed nodes
smg analyze --summary --top 5      # hotspots and key findings only
smg analyze --churn-days 180       # look back 6 months for churn (default: 90)
smg analyze --format json          # structured output for agents
```

### Graph-theoretic analyses

| Analysis | What it finds | Why it matters |
|----------|--------------|----------------|
| Cycle detection | Circular dependencies between modules/classes. Uses Tarjan's algorithm for strongly connected components. [Tarjan (1972)][tarjan] | Cycles prevent independent deployment and testing -- they force you to change and release coupled components together. |
| Topological layering | Assigns each node a layer based on dependency depth (layer 0 = leaves with no outgoing deps). | Reveals the architecture's depth. Tall, narrow layer stacks suggest long dependency chains; wide layers suggest parallel modules. |
| PageRank | Ranks nodes by recursive importance -- a node is important if important nodes depend on it. [Brin & Page (1998)][pagerank] | Identifies load-bearing abstractions: the modules that, if broken, cascade failures through the most dependents. |
| Betweenness centrality | Measures how often a node lies on shortest paths between other nodes. [Brandes (2001)][brandes] | Nodes with high betweenness are structural bottlenecks -- information and control flow must pass through them. Changing them has outsized risk. |
| k-core decomposition | Finds the maximal subgraph where every node has at least _k_ connections. [Seidman (1983)][seidman] | The innermost core is the tightly coupled heart of the architecture. If it's large, the system may be hard to decompose. |
| Bridge detection | Edges whose removal disconnects part of the graph. | Bridges are fragile -- they represent sole paths between components. Redundant paths (no bridges) indicate a more resilient architecture. |
| Fan-in / fan-out | Per-node counts of incoming (fan-in) and outgoing (fan-out) coupling edges. | High fan-in means a node is heavily depended on (risky to change). High fan-out means a node depends on many others (sensitive to their changes). |
| Dead code detection | Nodes with zero incoming coupling edges (no callers, no importers), excluding modules, packages, and known entry points. | Dead code inflates the codebase without providing value. Removing it reduces maintenance burden and cognitive load. |
| Layering violations | Coupling edges where the source is at the same or lower topological layer than the target -- back-dependencies. | These are the specific edges that create cycles or violate the intended dependency flow. They tell you which edges to remove to restore clean layering. |

### OO metrics

The CK suite ([Chidamber & Kemerer, 1994][ck]) and Martin's package metrics ([Martin, 1994][martin]) quantify class-level and module-level design quality.

| Metric | Per | Description |
|--------|-----|-------------|
| WMC | class | Weighted Methods per Class -- sum of cyclomatic complexity of all methods. High WMC indicates a class that does too much. |
| DIT | class | Depth of Inheritance Tree -- how many ancestors a class has. Deep trees increase complexity and fragility. |
| NOC | class | Number of Children -- direct subclass count. Many children suggest a class is a key abstraction (or overused as a base). |
| CBO | class | Coupling Between Objects -- number of distinct external classes this class couples to. High CBO makes classes hard to reuse and test. |
| RFC | class | Response For a Class -- methods in the class plus distinct methods they directly call. High RFC means more potential behavior to test. |
| LCOM4 | class | Lack of Cohesion of Methods -- number of connected components in the intra-class method call graph. LCOM4 > 1 means the class has disjoint responsibilities and should likely be split. [Hitz & Montazeri (1995)][lcom4] |
| Ca / Ce | module | Afferent (incoming) / efferent (outgoing) coupling -- how many other modules depend on this one, and how many it depends on. |
| Instability | module | Ce / (Ca + Ce). Ranges from 0 (stable, heavily depended upon) to 1 (unstable, depends on others). |
| Abstractness | module | Ratio of interfaces to total classes. Ranges from 0 (all concrete) to 1 (all abstract). |
| Distance | module | \|A + I - 1\| -- distance from the "main sequence" line where A + I = 1. Modules far from this line are either too abstract for their stability or too concrete for their instability. |
| SDP violations | module | Cases where a stable module depends on an unstable module, violating the Stable Dependencies Principle. Dependencies should flow toward stability. |

### Code smells

These patterns indicate structural problems that make code harder to change.

| Smell | Detection rule | What it means |
|-------|---------------|---------------|
| God Class | WMC >= 20 AND CBO >= 5 AND LCOM4 >= 2 | A class with too many responsibilities -- complex, coupled, and incohesive. Should be split. [Fowler (1999)][fowler] |
| Feature Envy | Method references another class's members more than its own (>= 2 external refs) | The method probably belongs in the other class. Moving it improves cohesion in both classes. |
| Shotgun Surgery | Function/method with coupling fan-out >= 7 | Changing this function likely requires coordinated changes across many dependents. Reducing fan-out isolates change. |
| God File | Module with high total cyclomatic complexity, many functions, or many external concerns | A file doing too much. Split into focused modules to reduce cognitive load and merge conflicts. |

### Git churn

`smg analyze` integrates temporal data from git history alongside the static graph analysis. For each entity in the graph, it counts how many commits modified the entity's line range over a configurable time window (default: 90 days).

Entities that are both structurally central (high complexity, high coupling) AND frequently changed are the most dangerous hotspots -- they are hard to modify correctly AND are being modified often.

Churn feeds into the hotspot ranking:
- **Class-level**: entities with > 10 touches get a churn bonus in their hotspot score.
- **Function-level**: functions with > 5 touches AND cyclomatic complexity > 10 are surfaced as churn hotspots even if they don't appear in the class-level rankings.

```bash
smg analyze --churn-days 30   # last month only
smg analyze --churn-days 365  # full year
```

### Hotspot synthesis

All analyses feed into a composite **hotspot ranking** that scores nodes by a weighted combination of:

- Complexity (WMC, cyclomatic complexity)
- Coupling (CBO, fan-out)
- Cohesion (LCOM4)
- Centrality (betweenness, PageRank)
- Churn (commit touch frequency)
- Module distance from the main sequence

The resulting ranked list surfaces the areas most likely to cause problems when modified.

## Architectural constraints

`smg analyze` tells you what *is* true about your architecture. `smg rule` and `smg check` let you declare what *should* be true -- and find where the code departs from intent.

This is inspired by Alloy's approach to software design ([Jackson, 2012][alloy]): state structural properties declaratively, then check them automatically. When a rule is violated, smg reports the specific offending edges or nodes -- concrete counterexamples, not just "violated: true."

### Path denial rules

Forbid coupling edges that match a glob pattern:

```bash
# No module in infra/ may depend on app/
smg rule add layering --deny "infra.* -> app.*"

# Controllers must not directly call repository code
smg rule add no-direct-db --deny "*.controller -[calls]-> *.repository"
```

Patterns use `fnmatch` syntax over fully-qualified node names. The optional `[rel]` filter restricts to a specific relationship type; without it, all coupling edges (calls, imports, inherits, implements, depends_on) are checked.

### Structural invariants

Bind existing analyses to named, persistent rules:

```bash
smg rule add acyclic --invariant no-cycles
smg rule add reachable --invariant no-dead-code --entry-points "main,cli.*"
smg rule add layered --invariant no-layering-violations
```

| Invariant | What it checks |
|-----------|---------------|
| `no-cycles` | No circular dependencies (Tarjan's SCC) |
| `no-dead-code` | Every non-entry node has at least one incoming coupling edge |
| `no-layering-violations` | No back-dependency edges violate topological layering |

### Checking rules

```bash
smg check                  # check all rules
smg check layering         # check one rule
smg check --format json    # structured output for agents / CI
```

Exit code 0 means all rules pass; exit code 1 means at least one violation. This makes `smg check` suitable as a CI gate:

```bash
smg scan src/ --clean && smg check
```

Rules are stored in `.smg/rules` (JSONL, same format as the graph) and persist across sessions.

## Node types

`package`, `module`, `class`, `function`, `method`, `interface`, `variable`, `constant`, `type`, `endpoint`, `config` -- plus any custom string.

## Relationship types

`calls`, `inherits`, `implements`, `contains`, `depends_on`, `imports`, `returns`, `accepts`, `overrides`, `decorates`, `tests` -- plus any custom string.

## Data format

`.smg/graph.jsonl` -- one JSON object per line:

```jsonl
{"kind":"node","name":"app.core.Engine","type":"class","file":"src/app/core.py","line":12,"docstring":"The engine.","metadata":{"source":"scan","content_hash":"a1b2c3d4e5f6a7b8","structure_hash":"f8e7d6c5b4a39281","metrics":{...}}}
{"kind":"edge","source":"app.core","rel":"contains","target":"app.core.Engine","metadata":{"source":"scan"}}
```

Git-friendly, human-readable, parseable with zero tooling. Nodes sorted by name, edges by (source, rel, target). Written atomically via temp file + rename.

## Name resolution

Node names are fully qualified (`app.core.Engine.run`), but you can use short names:

```bash
smg about Engine          # Matches app.core.Engine if unambiguous
smg show run              # Error if multiple matches -- lists candidates
```

## Design principles

- **Agent-first**: JSON by default when piped, structured output, exit codes for branching
- **Gradual disclosure**: `about` -> `show` -> `query` -- start simple, drill down as needed
- **Language-agnostic**: tree-sitter grammars for any language, BranchMap protocol for metrics
- **Incremental**: `--changed` rescans only modified files, `watch` for live updates
- **Provenance-aware**: scan vs manual annotations tracked, manual edges survive rescans
- **Zero config**: `smg init && smg scan .` works on any supported project
- **Git-friendly**: JSONL is diffable, sorted deterministically, written atomically

## References

- McCabe, T.J. (1976). [A Complexity Measure](https://doi.org/10.1109/TSE.1976.233837). *IEEE TSE*, SE-2(4), 308--320.
- Tarjan, R.E. (1972). [Depth-First Search and Linear Graph Algorithms](https://doi.org/10.1137/0201010). *SIAM Journal on Computing*, 1(2), 146--160.
- Seidman, S.B. (1983). [Network Structure and Minimum Degree](https://doi.org/10.1016/0378-8733(83)90028-X). *Social Networks*, 5(3), 269--287.
- Chidamber, S.R. & Kemerer, C.F. (1994). [A Metrics Suite for Object Oriented Design](https://doi.org/10.1109/32.295895). *IEEE TSE*, 20(6), 476--493.
- Martin, R.C. (1994). [OO Design Quality Metrics: An Analysis of Dependencies](https://doi.org/10.1007/978-1-4612-4316-3_9). *OOPSLA '94 Workshop*.
- Hitz, M. & Montazeri, B. (1995). [Measuring Coupling and Cohesion in Object-Oriented Systems](https://scholar.google.com/scholar?q=Hitz+Montazeri+1995+Measuring+Coupling+Cohesion). *Proc. ISACC '95*.
- Jaccard, P. (1912). [The Distribution of the Flora in the Alpine Zone](https://doi.org/10.1111/j.1469-8137.1912.tb05611.x). *New Phytologist*, 11(2), 37--50.
- Brin, S. & Page, L. (1998). [The Anatomy of a Large-Scale Hypertextual Web Search Engine](https://doi.org/10.1016/S0169-7552(98)00110-X). *Computer Networks*, 30(1--7), 107--117.
- Fowler, M. (1999). [Refactoring: Improving the Design of Existing Code](https://martinfowler.com/books/refactoring.html). Addison-Wesley.
- Brandes, U. (2001). [A Faster Algorithm for Betweenness Centrality](https://doi.org/10.1080/0022250X.2001.9990249). *Journal of Mathematical Sociology*, 25(2), 163--177.
- Jackson, D. (2012). [Software Abstractions: Logic, Language, and Analysis](https://mitpress.mit.edu/9780262017152/). MIT Press.
- Campbell, G.A. (2018). [Cognitive Complexity: An Overview and Evaluation](https://doi.org/10.1145/3194164.3194186). *Proc. TechDebt '18*, ACM.

<!-- Link definitions for inline references throughout the doc -->
[mccabe]: https://doi.org/10.1109/TSE.1976.233837
[tarjan]: https://doi.org/10.1137/0201010
[seidman]: https://doi.org/10.1016/0378-8733(83)90028-X
[ck]: https://doi.org/10.1109/32.295895
[martin]: https://doi.org/10.1007/978-1-4612-4316-3_9
[lcom4]: https://scholar.google.com/scholar?q=Hitz+Montazeri+1995+Measuring+Coupling+Cohesion
[jaccard]: https://doi.org/10.1111/j.1469-8137.1912.tb05611.x
[pagerank]: https://doi.org/10.1016/S0169-7552(98)00110-X
[fowler]: https://martinfowler.com/books/refactoring.html
[brandes]: https://doi.org/10.1080/0022250X.2001.9990249
[alloy]: https://mitpress.mit.edu/9780262017152/
[cognitive]: https://doi.org/10.1145/3194164.3194186

## License

MIT
