# TODO

Shipped items below describe the current release. Later ideas remain future
work.

## [done] Declarative architectural constraints

Shipped in `smg rule` / `smg check`. Path denial rules and structural invariants (no-cycles, no-dead-code, no-layering-violations) with counterexample-driven output.

## [done] DSM export

Shipped in `smg export dsm`. Exports a Dependency Structure Matrix alongside Mermaid/DOT/JSON. A DSM is a square matrix where cell (i,j) indicates module i depends on module j.

Based on: Sangal, N. et al. (2005). "Using Dependency Models to Manage Complex Software Architecture." *OOPSLA '05*. [PDF](https://groups.csail.mit.edu/sdg/pubs/2005/oopsla05-dsm.pdf)

## [done] Quantified constraint rules

Shipped in `smg rule add --forall ... --assert ...` and `smg check`. Universal
per-subject constraints now evaluate graph metrics, OO metrics, and scanner
metadata without falling back to Python evaluation.

```bash
smg rule add service-fan-out --forall "*.service" --assert "fan_out <= 5"
```

The current release intentionally stops short of graph-wide aggregates such as
`count(...)` or `sum(...)`.

## [done] Minimal violation witnesses

Shipped in `smg check` text and JSON output. Violations now expose minimal
`witnesses` alongside the legacy `edges`, `nodes`, and `cycles` projections, so
CI failures can point at concrete counterexamples instead of only aggregate
counts.

Based on: Alloy's counterexample-driven analysis. Jackson, D. (2019). "Alloy: A Language and Tool for Exploring Software Designs." *CACM* 62(9), 66-76.

## [done] Concept and group analysis

Shipped in `smg concept` and `smg analyze --concepts`. Declarations live in
`.smg/concepts`, separate from `.smg/graph.jsonl`, and the release reports the
cross-group signals needed for architecture review:

- Concept independence checking
- Sync surface analysis

This ships as an analysis surface rather than a `smg check` invariant.

Based on: Jackson, D. (2021). *The Essence of Software: Why Concepts Matter for Design.* Princeton University Press. Meng, E. & Jackson, D. (2025). "What You See Is What It Does." *Onward! at SPLASH '25'*. [arXiv](https://arxiv.org/abs/2508.14511)

## Later ideas

### Concept independence as a check

Promote `smg analyze --concepts` violations into a dedicated `smg check`
invariant or quantified rule once the concept payload and sync-point semantics
settle. Today the repo can report cross-concept coupling, but it does not fail
CI on that signal by itself.

### Community detection (label propagation)

Find natural module clusters from the coupling graph structure. Compare against declared package boundaries to find misplaced code. Simpler than Louvain, still useful for identifying modules that don't match their declared homes.

### Overloaded module detection

Flag modules with high betweenness centrality AND edges into multiple otherwise-disconnected clusters. This is the graph-level signature of an "overloaded concept" -- a module serving multiple unrelated purposes that should be split.

Based on: Jackson's concept design framework. The "overloaded concept" is the primary design smell in *Essence of Software*.

### HITS (Hub/Authority)

Kleinberg's algorithm. Distinguishes hubs (orchestrators that call many things) from authorities (core utilities called by many). Different signal from PageRank -- same iterative power-method pattern.

### Change coupling (co-change analysis)

Nodes that always change together in git history but have no structural edge. Requires integrating `git log`. Surfaces hidden dependencies that static analysis misses.

## References

- Sangal, N., Jordan, E., Sinha, V. & Jackson, D. (2005). "Using Dependency Models to Manage Complex Software Architecture." *OOPSLA '05'*. [PDF](https://groups.csail.mit.edu/sdg/pubs/2005/oopsla05-dsm.pdf)
- Jackson, D. (2021). *The Essence of Software: Why Concepts Matter for Design.* Princeton University Press.
- Jackson, D. (2012). *Software Abstractions: Logic, Language, and Analysis.* MIT Press.
- Jackson, D. (2019). "Alloy: A Language and Tool for Exploring Software Designs." *CACM* 62(9), 66-76.
- Meng, E. & Jackson, D. (2025). "What You See Is What It Does." *Onward! at SPLASH '25'*. [arXiv](https://arxiv.org/abs/2508.14511)
- O'Callahan, R. & Jackson, D. (1997). "Lackwit: A Program Understanding Tool Based on Type Inference." *ICSE '97*.
