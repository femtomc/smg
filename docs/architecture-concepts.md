# Architecture Concepts

`smg concept` declarations group graph nodes into higher-level architectural
concepts. A concept owns the nodes under one or more prefixes. A sync point is a
node-name prefix that is allowed to cross a concept boundary.

Use concept analysis as a calibration report before enabling it as a hard rule:

```bash
uv run --with-editable . --extra dev --extra scan python -m smg analyze --concepts --summary --format json
```

When the reported crossings match the intended public seams, add the invariant:

```bash
uv run --with-editable . --extra dev --extra scan python -m smg rule add boundaries --invariant concept-boundaries
uv run --with-editable . --extra dev --extra scan python -m smg check --format json
```

## First-Party Calibration

The current repository naturally separates into these concepts:

```bash
smg concept add core --prefix smg.graph --prefix smg.model --prefix smg.storage
smg concept add scan --prefix smg.scan --prefix smg.langs
smg concept add analysis --prefix smg.analyze --prefix smg.graph_metrics --prefix smg.oo_metrics --prefix smg.churn --prefix smg.context --prefix smg.diff --prefix smg.export --prefix smg.blame
smg concept add enforce --prefix smg.rules --prefix smg.rule_expr --prefix smg.concepts --prefix smg.witness
smg concept add cli --prefix smg.cli
```

Those declarations are intentionally broad. They should not become a failing
gate without sync points, because the CLI is expected to call scan, analysis,
and enforcement entry points, and most subsystems are expected to depend on the
core graph/model types.

Start with these sync-point candidates:

```bash
smg concept add core --prefix smg.graph --prefix smg.model --prefix smg.storage \
  --sync-point smg.graph --sync-point smg.model --sync-point smg.storage
smg concept add scan --prefix smg.scan --prefix smg.langs \
  --sync-point smg.scan.scan_paths --sync-point smg.scan.changed_files
smg concept add analysis --prefix smg.analyze --prefix smg.graph_metrics --prefix smg.oo_metrics --prefix smg.churn --prefix smg.context --prefix smg.diff --prefix smg.export --prefix smg.blame \
  --sync-point smg.analyze.run_analysis --sync-point smg.analyze.filter_to_delta --sync-point smg.diff.diff_graphs --sync-point smg.diff.load_graph_from_git
smg concept add enforce --prefix smg.rules --prefix smg.rule_expr --prefix smg.concepts --prefix smg.witness \
  --sync-point smg.rules.check_all --sync-point smg.rules.check_rule --sync-point smg.concepts.analyze_concepts
smg concept add cli --prefix smg.cli \
  --sync-point smg.cli
```

After each adjustment, rerun `smg analyze --concepts --summary --format json`.
Only add `concept-boundaries` to `smg check` when the remaining violations are
unexpected architecture crossings rather than normal public API usage.

This repository's validation script now performs that calibrated setup
automatically before `smg check`: it unions the first-party concept declarations
and sync points into `.smg/concepts`, then ensures a `concept-boundaries` rule
exists in `.smg/rules`.

The JSON report separates total cross-concept dependency counts from
`unsanctioned_count`. For each violation, `sync_candidates.source` lists
offending source nodes that could become source-side sync points, and
`sync_candidates.target` lists target nodes that could become target-side sync
points. The same violation includes `sync_commands` with concrete
`smg concept sync-point NAME PREFIX` commands for those candidates. Treat those
commands as review prompts, not automatic fixes.
