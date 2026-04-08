# Release Design Record

This release extends the baseline `smg` workflow in three places:

- quantified rules in `smg rule add --forall ... --assert ...`
- minimal witnesses in `smg check`
- declared concept analysis in `smg concept ...` and `smg analyze --concepts`

The public release story stays centered on those three additions. DSM export,
scan/query/analyze, and the existing invariant checks remain part of the shipped
baseline rather than future work.

The canonical editable contributor workflow is:

```bash
uv run --with-editable . --extra dev --extra scan python -m pytest -q
uv run --with-editable . --extra dev --extra scan python -m pyright
```

`README.md` is the user-facing entry point for those commands. This document
records the storage, CLI, and JSON shapes that shipped on the current branch.

## Release Shape

The release keeps the storage model split by responsibility:

- `.smg/graph.jsonl` stores the code graph: scanned nodes, scanned edges, and
  manual graph annotations.
- `.smg/rules` stores architectural rule declarations.
- `.smg/concepts` stores declared concept boundaries.

That split is intentional. Rules and concepts are declarations *about* the
graph, not graph entities. Keeping them out of `.smg/graph.jsonl` preserves the
existing meanings of graph counts, dead-code detection, layering analysis, and
similar metrics.

The release also keeps two compatibility boundaries in place:

- `smg analyze` only adds concept output when `--concepts` is requested.
- Concept analysis remains an analysis surface. It reports unsanctioned
  cross-concept edges, but it does not create a new `smg check` invariant in
  this release.

## Quantified Rules

### CLI Surface

`smg rule add` now supports a quantified path alongside the existing deny and
invariant paths:

```bash
smg rule add service-fan-out --forall "*.service" --assert "fan_out <= 5"
smg rule add complex-handler --forall "api.handlers.*" --assert "cyclomatic_complexity <= 10"
smg rule add shallow-package --forall "smg.cli.*" --assert "layer >= 2" --scope smg
```

The CLI contract is:

- exactly one of `--deny`, `--invariant`, or `--forall` must be present
- `--assert` is required with `--forall`
- `--scope` keeps its existing prefix-scoping meaning

This release supports only universal per-subject checks. It does not add
graph-wide aggregates such as `count(...)` or `sum(...)`.

### Persistence Model

Quantified rules reuse the existing rule store in `.smg/rules`. A quantified
record looks like this:

```json
{
  "kind": "rule",
  "name": "service-fan-out",
  "type": "quantified",
  "selector": "*.service",
  "assertion": "fan_out <= 5",
  "scope": "smg"
}
```

The shipped rule schema is:

| Field | Meaning |
| --- | --- |
| `name` | Stable rule identifier |
| `type` | `deny`, `invariant`, or `quantified` |
| `pattern` | Deny-rule pattern |
| `invariant` | Invariant name |
| `selector` | Glob over fully-qualified subject names for quantified rules |
| `assertion` | Parsed threshold expression for quantified rules |
| `params` | Invariant-specific extras such as `entry_points` |
| `scope` | Optional module-prefix scope |

Existing `.smg/rules` records continue to load unchanged.

### Assertion Language

The quantified assertion language is intentionally small:

- literals: integers, floats, booleans, quoted strings
- identifiers: metric names
- unary `not`
- binary `+`, `-`, `*`, `/`
- comparisons: `==`, `!=`, `<`, `<=`, `>`, `>=`
- boolean `and`, `or`
- parentheses

There is no arbitrary Python evaluation. Assertions parse through
`src/smg/rule_expr.py` into a small AST, then evaluate against a per-subject
fact bag.

### Metric Surface

Quantified rules evaluate existing per-node facts rather than introducing a
second analysis model. The shipped identifier catalog is:

- graph metrics from `src/smg/graph_metrics.py`:
  `fan_in`, `fan_out`, `layer`, `pagerank`, `betweenness`, `kcore`
- boolean graph facts:
  `dead`, `in_cycle`
- scanner metadata:
  `cyclomatic_complexity`, `cognitive_complexity`, `nesting`
- class metrics from `src/smg/oo_metrics.py`:
  `wmc`, `cbo`, `rfc`, `lcom4`, `dit`, `noc`, `max_method_cc`
- module and package metrics from `src/smg/oo_metrics.py`:
  `instability`, `abstractness`, `distance`

`smg check` parses quantified assertions up front, discovers which identifiers
they reference, and computes metric maps lazily through
`QuantifiedMetricCatalog`. That keeps quantified checks additive without making
every `smg check` invocation pay the full `run_analysis()` cost.

### Evaluation Semantics

Quantified rule evaluation is:

1. Load the graph and rules from the existing stores.
2. Parse quantified assertions and reject unknown identifiers.
3. Select subjects by `fnmatch` over fully-qualified node names.
4. Apply `--scope` as the existing dotted-prefix filter.
5. Build the subject fact bag from lazily computed metric maps.
6. Evaluate the assertion once per subject.
7. Emit one witness per failing subject.

Important edge cases:

- Zero matched subjects are a vacuous pass.
- Unknown metric identifiers are rejected when the rule is added.
- If a metric is known in general but undefined for the matched subject type,
  `smg check` treats that as a configuration error. For example, `wmc` is valid
  for classes but not for packages.

## Witness Model

`smg check` now treats a violation as a summary plus a list of minimal
counterexamples:

```text
Violation
  summary message
  witnesses: list[Witness]
```

The shipped witness kinds are:

- `edge`: one offending coupling edge
- `node`: one offending node
- `cycle`: one minimal cycle
- `predicate`: one quantified-rule subject plus the observed facts

A quantified witness looks like this:

```json
{
  "kind": "predicate",
  "subject": "smg.cli.explore.analyze",
  "assertion": "fan_out <= 5",
  "facts": {
    "fan_out": 9
  }
}
```

### Compatibility

`Violation.to_dict()` stays additive:

- `rule`, `type`, and `message` remain unchanged
- `witnesses` is always the primary structured payload for new consumers
- legacy `edges`, `nodes`, and `cycles` projections remain populated for old
  consumers

That means:

- deny and layering violations still populate `edges`
- dead-code violations still populate `nodes`
- cycle violations still populate `cycles`
- quantified violations populate `nodes` with failing subjects and `witnesses`
  with the observed assertion facts

### Minimality Rules

Minimality is per witness, not per violation:

- deny rule: one forbidden edge
- `no-layering-violations`: one back-dependency edge
- `no-cycles`: one minimal cycle from `graph_metrics.minimal_cycle`
- `no-dead-code`: one unreachable node
- quantified rule: one failing subject and the smallest fact bag needed to
  explain the failure

Text output keeps the existing PASS/FAIL framing and prints the first few
witnesses before any broader projections.

## Concepts And Groups

### Separate Store

Concepts remain sidecar declarations rather than graph nodes. The release uses
`.smg/concepts`, loaded and saved through `src/smg/storage.py`, so concept
metadata does not distort the code-shaped graph in `.smg/graph.jsonl`.

### Declaration Model

The release supports explicit, prefix-based declarations:

```bash
smg concept add cli --prefix smg.cli
smg concept add scanners --prefix smg.scan --prefix smg.langs
smg concept add core --prefix smg.graph --prefix smg.model --sync-point smg.graph.SemGraph
```

Persisted records look like this:

```json
{
  "kind": "concept",
  "name": "core",
  "prefixes": ["smg.graph", "smg.model"],
  "sync_points": ["smg.graph.SemGraph"]
}
```

The `prefixes` field stays narrower than a general glob language. That matches
the existing prefix-scoping model already used by `smg analyze --module` and
rule `scope`.

### Materialization Semantics

Concept materialization happens at analysis time:

1. Resolve each declared prefix against package and module nodes.
2. Collapse overlapping anchors so parent prefixes own the subtree once.
3. Expand each anchor to all descendants by dotted-prefix membership.
4. Build a concrete owner map from graph node to concept.
5. Reject overlapping ownership as a configuration error.

Two shipped semantics matter:

- Ownership is disjoint in this release. A graph node belongs to at most one
  concept.
- Sync points are node-name prefixes. A cross-concept edge is allowed if the
  source node matches a sync point from the source concept or the target node
  matches a sync point from the target concept.

### CLI And Analysis Surface

The concept CLI is a top-level group parallel to `rule`:

```bash
smg concept add ...
smg concept list
smg concept rm ...
```

Concept analysis is an explicit opt-in on `smg analyze`:

```bash
smg analyze --concepts
smg analyze --concepts --format json
```

When `--concepts` is present, `smg analyze --format json` adds a `concepts`
section with three payloads:

- `declared`: per-concept summaries
- `dependencies`: lifted cross-concept dependency edges
- `violations`: unsanctioned cross-concept edges

The per-concept summary includes:

- `members`
- `internal_edges`
- `cross_in`
- `cross_out`
- `sync_density`
- `sync_fan_out`
- `sync_asymmetry`

The `dependencies` payload is the bridge from raw graph edges to concept-level
summaries. Each dependency record includes relation counts, representative edge
witnesses, and `allowed_sync` to distinguish sanctioned sync paths from
unsanctioned coupling.

### Concept Independence Semantics

Concept analysis is intentionally not a `smg check` invariant in this release.
`smg analyze --concepts` reports violations for cross-concept edges that are
not covered by a declared sync point, but `smg check` does not fail CI on that
signal by itself.

## Code Layout And Coverage

The shipped release surfaces live here:

- rules and witness shaping:
  `src/smg/rules.py`, `src/smg/rule_expr.py`, `src/smg/witness.py`,
  `src/smg/cli/enforce.py`, `src/smg/storage.py`
- concept declarations and analysis:
  `src/smg/concepts.py`, `src/smg/cli/concepts.py`, `src/smg/analyze.py`,
  `src/smg/cli/explore.py`, `src/smg/storage.py`
- test coverage:
  `tests/test_rules.py`, `tests/test_metrics_properties.py`,
  `tests/test_concepts.py`, and `tests/test_cli.py`

The release does not change the base graph schema.

## Compatibility And Limits

- `.smg/graph.jsonl` remains unchanged.
- Existing `.smg/rules` records remain valid.
- Absence of `.smg/concepts` means "no declarations," not "broken analysis."
- `smg check --format json` still returns `rules_checked`, `violations`, and
  `status`.
- New consumers should read `violation.witnesses`; old consumers can keep using
  `edges`, `nodes`, and `cycles`.
- `smg analyze` only emits concept output when `--concepts` is requested.
- The release does not add inferred concepts, community detection, or
  graph-wide quantified aggregates.

## References

- Jackson, D. (2012). *Software Abstractions: Logic, Language, and Analysis*.
  MIT Press.
- Jackson, D. (2019). "Alloy: A Language and Tool for Exploring Software
  Designs." *CACM* 62(9), 66-76.
- Jackson, D. (2021). *The Essence of Software: Why Concepts Matter for
  Design.* Princeton University Press.
- Meng, E. & Jackson, D. (2025). "What You See Is What It Does." *Onward! at
  SPLASH '25'*. [arXiv](https://arxiv.org/abs/2508.14511)
