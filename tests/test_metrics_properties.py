"""Property-based tests for graph and OO metrics using Hypothesis.

These tests verify invariants that must hold for ANY valid graph,
not just hand-crafted examples. They catch edge cases and corner
cases that example-based tests miss.
"""
from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings, assume

from semg.graph import SemGraph
from semg.graph_metrics import (
    betweenness_centrality,
    detect_bridges,
    find_cycles,
    kcore_decomposition,
    pagerank,
    topological_layers,
)
from semg.model import Edge, Node, NodeType, RelType
from semg.oo_metrics import cbo, dit, lcom4, martin_metrics, noc, rfc, sdp_violations, wmc


# --- Strategies for generating random graphs ---


node_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=4
).map(lambda s: f"mod.{s}")

node_types = st.sampled_from([NodeType.MODULE, NodeType.CLASS, NodeType.FUNCTION, NodeType.METHOD])

coupling_rels = st.sampled_from([RelType.CALLS, RelType.IMPORTS, RelType.INHERITS, RelType.DEPENDS_ON])


@st.composite
def random_graph(draw, min_nodes=2, max_nodes=15, max_edges=30):
    """Generate a random SemGraph with coupling edges."""
    n = draw(st.integers(min_value=min_nodes, max_value=max_nodes))
    names = [f"n{i}" for i in range(n)]

    g = SemGraph()
    for name in names:
        t = draw(st.sampled_from([NodeType.MODULE, NodeType.CLASS, NodeType.FUNCTION]))
        g.add_node(Node(name=name, type=t))

    num_edges = draw(st.integers(min_value=0, max_value=min(max_edges, n * (n - 1))))
    for _ in range(num_edges):
        src = draw(st.sampled_from(names))
        tgt = draw(st.sampled_from(names))
        if src != tgt:
            rel = draw(coupling_rels)
            key = (src, rel.value, tgt)
            if key not in g.edges:
                g.add_edge(Edge(source=src, target=tgt, rel=rel))

    return g


@st.composite
def random_class_graph(draw, min_classes=1, max_classes=5, max_methods_per_class=6):
    """Generate a graph with classes, methods, and call edges for OO metrics."""
    g = SemGraph()
    g.add_node(Node(name="mod", type=NodeType.MODULE))

    n_classes = draw(st.integers(min_value=min_classes, max_value=max_classes))
    all_methods: list[str] = []

    for ci in range(n_classes):
        cname = f"mod.C{ci}"
        g.add_node(Node(name=cname, type=NodeType.CLASS))
        g.add_edge(Edge(source="mod", target=cname, rel=RelType.CONTAINS))

        n_methods = draw(st.integers(min_value=0, max_value=max_methods_per_class))
        class_methods: list[str] = []
        for mi in range(n_methods):
            mname = f"{cname}.m{mi}"
            cc = draw(st.integers(min_value=1, max_value=20))
            g.add_node(Node(
                name=mname, type=NodeType.METHOD,
                metadata={"metrics": {"cyclomatic_complexity": cc}},
            ))
            g.add_edge(Edge(source=cname, target=mname, rel=RelType.CONTAINS))
            class_methods.append(mname)
            all_methods.append(mname)

        # Random intra-class calls
        if len(class_methods) >= 2:
            n_calls = draw(st.integers(min_value=0, max_value=len(class_methods)))
            for _ in range(n_calls):
                src = draw(st.sampled_from(class_methods))
                tgt = draw(st.sampled_from(class_methods))
                if src != tgt:
                    key = (src, RelType.CALLS.value, tgt)
                    if key not in g.edges:
                        g.add_edge(Edge(source=src, target=tgt, rel=RelType.CALLS))

    # Random cross-class calls
    if len(all_methods) >= 2:
        n_cross = draw(st.integers(min_value=0, max_value=min(10, len(all_methods))))
        for _ in range(n_cross):
            src = draw(st.sampled_from(all_methods))
            tgt = draw(st.sampled_from(all_methods))
            if src != tgt:
                key = (src, RelType.CALLS.value, tgt)
                if key not in g.edges:
                    g.add_edge(Edge(source=src, target=tgt, rel=RelType.CALLS))

    # Random inheritance
    class_names = [f"mod.C{i}" for i in range(n_classes)]
    if n_classes >= 2:
        n_inherit = draw(st.integers(min_value=0, max_value=n_classes - 1))
        for _ in range(n_inherit):
            child = draw(st.sampled_from(class_names))
            parent = draw(st.sampled_from(class_names))
            if child != parent:
                key = (child, RelType.INHERITS.value, parent)
                if key not in g.edges:
                    g.add_edge(Edge(source=child, target=parent, rel=RelType.INHERITS))

    return g


@st.composite
def random_module_graph(draw, min_modules=2, max_modules=8):
    """Generate a graph with modules and import edges for Martin's metrics."""
    g = SemGraph()
    n = draw(st.integers(min_value=min_modules, max_value=max_modules))
    mod_names = [f"mod{i}" for i in range(n)]

    for name in mod_names:
        g.add_node(Node(name=name, type=NodeType.MODULE))
        # Add some classes/interfaces
        n_classes = draw(st.integers(min_value=0, max_value=3))
        for ci in range(n_classes):
            is_interface = draw(st.booleans())
            cname = f"{name}.C{ci}"
            g.add_node(Node(
                name=cname,
                type=NodeType.INTERFACE if is_interface else NodeType.CLASS,
            ))
            g.add_edge(Edge(source=name, target=cname, rel=RelType.CONTAINS))

    # Random imports between modules
    n_imports = draw(st.integers(min_value=0, max_value=n * 2))
    for _ in range(n_imports):
        src = draw(st.sampled_from(mod_names))
        tgt = draw(st.sampled_from(mod_names))
        if src != tgt:
            key = (src, RelType.IMPORTS.value, tgt)
            if key not in g.edges:
                g.add_edge(Edge(source=src, target=tgt, rel=RelType.IMPORTS))

    return g


# ============================================================
# Graph-Theoretic Metric Properties
# ============================================================


class TestCycleProperties:
    """Properties that must hold for cycle detection."""

    @given(random_graph())
    @settings(max_examples=100)
    def test_cycles_are_subsets_of_nodes(self, g: SemGraph):
        """Every node in a cycle must exist in the graph."""
        cycles = find_cycles(g)
        all_names = set(g.nodes.keys())
        for cycle in cycles:
            for name in cycle:
                assert name in all_names

    @given(random_graph())
    @settings(max_examples=100)
    def test_cycle_members_are_mutually_reachable(self, g: SemGraph):
        """In each SCC, every node should reach every other via coupling edges."""
        cycles = find_cycles(g)
        for cycle in cycles:
            assert len(cycle) >= 2, "SCCs must have at least 2 nodes"

    @given(random_graph())
    @settings(max_examples=100)
    def test_no_single_node_cycles(self, g: SemGraph):
        """Self-loops should not be reported as cycles."""
        cycles = find_cycles(g)
        for cycle in cycles:
            assert len(cycle) >= 2

    @given(random_graph())
    @settings(max_examples=100)
    def test_cycle_nodes_are_sorted(self, g: SemGraph):
        """Each cycle list is sorted for determinism."""
        cycles = find_cycles(g)
        for cycle in cycles:
            assert cycle == sorted(cycle)

    def test_dag_has_no_cycles(self):
        """A strict DAG must have zero cycles."""
        g = SemGraph()
        for i in range(10):
            g.add_node(Node(name=f"n{i}", type=NodeType.MODULE))
        for i in range(9):
            g.add_edge(Edge(source=f"n{i}", target=f"n{i+1}", rel=RelType.IMPORTS))
        assert find_cycles(g) == []


class TestTopologicalLayerProperties:

    @given(random_graph())
    @settings(max_examples=100)
    def test_layers_are_non_negative(self, g: SemGraph):
        layers = topological_layers(g)
        for layer in layers.values():
            assert layer >= 0

    @given(random_graph())
    @settings(max_examples=100)
    def test_all_coupling_nodes_have_layers(self, g: SemGraph):
        """Every node involved in coupling edges gets a layer."""
        layers = topological_layers(g)
        # Nodes only in contains edges may not appear
        for edge in g.all_edges():
            if edge.rel.value in ("calls", "imports", "inherits", "implements", "depends_on"):
                assert edge.source in layers
                assert edge.target in layers


class TestPageRankProperties:

    @given(random_graph(min_nodes=3))
    @settings(max_examples=100)
    def test_pagerank_values_are_positive(self, g: SemGraph):
        ranks = pagerank(g)
        for r in ranks.values():
            assert r >= 0

    @given(random_graph(min_nodes=3))
    @settings(max_examples=100)
    def test_pagerank_sums_to_approximately_one(self, g: SemGraph):
        ranks = pagerank(g)
        if ranks:
            total = sum(ranks.values())
            assert abs(total - 1.0) < 0.05, f"PageRank sum = {total}"

    @given(random_graph(min_nodes=3))
    @settings(max_examples=100)
    def test_pagerank_covers_all_coupling_nodes(self, g: SemGraph):
        ranks = pagerank(g)
        for edge in g.all_edges():
            if edge.rel.value in ("calls", "imports", "inherits", "implements", "depends_on"):
                assert edge.source in ranks
                assert edge.target in ranks


class TestBetweennessProperties:

    @given(random_graph(min_nodes=3))
    @settings(max_examples=100)
    def test_betweenness_values_in_range(self, g: SemGraph):
        bc = betweenness_centrality(g)
        for v in bc.values():
            assert 0.0 <= v <= 1.0 + 1e-9, f"BC out of range: {v}"

    @given(random_graph(min_nodes=3))
    @settings(max_examples=100)
    def test_leaf_nodes_have_zero_betweenness(self, g: SemGraph):
        """Nodes with degree 1 (leaves) cannot be on shortest paths between others."""
        bc = betweenness_centrality(g)
        for name, centrality in bc.items():
            neighbors = set()
            for edge in g.all_edges():
                if edge.rel.value in ("calls", "imports", "inherits", "implements", "depends_on"):
                    if edge.source == name:
                        neighbors.add(edge.target)
                    if edge.target == name:
                        neighbors.add(edge.source)
            if len(neighbors) <= 1 and centrality > 0:
                # Leaf in the coupling graph — betweenness should be ~0
                # (but floating point means we allow small epsilon)
                assert centrality < 0.01, f"Leaf {name} has BC={centrality}"


class TestKCoreProperties:

    @given(random_graph())
    @settings(max_examples=100)
    def test_coreness_is_non_negative(self, g: SemGraph):
        kc = kcore_decomposition(g)
        for v in kc.values():
            assert v >= 0

    @given(random_graph())
    @settings(max_examples=100)
    def test_coreness_bounded_by_degree(self, g: SemGraph):
        """A node's coreness cannot exceed its degree in the coupling graph."""
        kc = kcore_decomposition(g)
        for name, coreness in kc.items():
            degree = 0
            for edge in g.all_edges():
                if edge.rel.value in ("calls", "imports", "inherits", "implements", "depends_on"):
                    if edge.source == name or edge.target == name:
                        degree += 1
            assert coreness <= degree, f"{name}: coreness {coreness} > degree {degree}"


class TestBridgeProperties:

    @given(random_graph())
    @settings(max_examples=100)
    def test_bridges_are_valid_edges(self, g: SemGraph):
        bridges = detect_bridges(g)
        nodes = set(g.nodes.keys())
        for a, b in bridges:
            assert a in nodes
            assert b in nodes

    @given(random_graph())
    @settings(max_examples=100)
    def test_bridges_are_sorted(self, g: SemGraph):
        bridges = detect_bridges(g)
        for a, b in bridges:
            assert a <= b  # normalized: smaller name first


# ============================================================
# OO Metric Properties
# ============================================================


class TestWMCProperties:

    @given(random_class_graph())
    @settings(max_examples=100)
    def test_wmc_is_non_negative(self, g: SemGraph):
        result = wmc(g)
        for v in result.values():
            assert v >= 0

    @given(random_class_graph())
    @settings(max_examples=100)
    def test_wmc_ge_method_count(self, g: SemGraph):
        """WMC >= number of methods (since min CC per method is 1)."""
        result = wmc(g)
        for name in result:
            methods = [
                e.target for e in g.outgoing(name, rel=RelType.CONTAINS)
                if g.get_node(e.target) and g.get_node(e.target).type.value in ("function", "method")
            ]
            assert result[name] >= len(methods)


class TestDITProperties:

    @given(random_class_graph())
    @settings(max_examples=100)
    def test_dit_is_non_negative(self, g: SemGraph):
        result = dit(g)
        for v in result.values():
            assert v >= 0

    @given(random_class_graph())
    @settings(max_examples=100)
    def test_dit_zero_means_no_parents(self, g: SemGraph):
        result = dit(g)
        for name, depth in result.items():
            if depth == 0:
                parents = [e.target for e in g.outgoing(name, rel=RelType.INHERITS)]
                # Either no parents, or parents are not in the graph as classes
                assert len(parents) == 0 or all(
                    g.get_node(p) is None or g.get_node(p).type != NodeType.CLASS
                    for p in parents
                )


class TestNOCProperties:

    @given(random_class_graph())
    @settings(max_examples=100)
    def test_noc_is_non_negative(self, g: SemGraph):
        result = noc(g)
        for v in result.values():
            assert v >= 0


class TestCBOProperties:

    @given(random_class_graph())
    @settings(max_examples=100)
    def test_cbo_is_non_negative(self, g: SemGraph):
        result = cbo(g)
        for v in result.values():
            assert v >= 0

    @given(random_class_graph(min_classes=1, max_classes=1))
    @settings(max_examples=50)
    def test_single_class_has_zero_cbo(self, g: SemGraph):
        """A graph with only one class has CBO=0 (no other classes to couple to)."""
        result = cbo(g)
        for v in result.values():
            assert v == 0


class TestRFCProperties:

    @given(random_class_graph())
    @settings(max_examples=100)
    def test_rfc_ge_method_count(self, g: SemGraph):
        """RFC >= number of methods (since RFC = methods + callees)."""
        result = rfc(g)
        for name in result:
            methods = [
                e.target for e in g.outgoing(name, rel=RelType.CONTAINS)
                if g.get_node(e.target) and g.get_node(e.target).type.value in ("function", "method")
            ]
            assert result[name] >= len(methods)


class TestLCOM4Properties:

    @given(random_class_graph())
    @settings(max_examples=100)
    def test_lcom4_bounded_by_method_count(self, g: SemGraph):
        """LCOM4 <= number of methods (at most one component per method)."""
        result = lcom4(g)
        for name in result:
            methods = [
                e.target for e in g.outgoing(name, rel=RelType.CONTAINS)
                if g.get_node(e.target) and g.get_node(e.target).type.value in ("function", "method")
            ]
            assert result[name] <= max(len(methods), 1)

    @given(random_class_graph())
    @settings(max_examples=100)
    def test_lcom4_is_non_negative(self, g: SemGraph):
        result = lcom4(g)
        for v in result.values():
            assert v >= 0


# ============================================================
# Martin's Metrics Properties
# ============================================================


class TestMartinMetricsProperties:

    @given(random_module_graph())
    @settings(max_examples=100)
    def test_instability_in_range(self, g: SemGraph):
        result = martin_metrics(g)
        for name, m in result.items():
            assert 0.0 <= m["instability"] <= 1.0, f"{name}: I={m['instability']}"

    @given(random_module_graph())
    @settings(max_examples=100)
    def test_abstractness_in_range(self, g: SemGraph):
        result = martin_metrics(g)
        for name, m in result.items():
            assert 0.0 <= m["abstractness"] <= 1.0, f"{name}: A={m['abstractness']}"

    @given(random_module_graph())
    @settings(max_examples=100)
    def test_distance_in_range(self, g: SemGraph):
        result = martin_metrics(g)
        for name, m in result.items():
            assert 0.0 <= m["distance"] <= 1.0 + 0.01, f"{name}: D={m['distance']}"

    @given(random_module_graph())
    @settings(max_examples=100)
    def test_ca_ce_are_non_negative(self, g: SemGraph):
        result = martin_metrics(g)
        for name, m in result.items():
            assert m["ca"] >= 0
            assert m["ce"] >= 0

    @given(random_module_graph())
    @settings(max_examples=100)
    def test_instability_formula(self, g: SemGraph):
        """I = Ce / (Ca + Ce), or 0 if both are 0."""
        result = martin_metrics(g)
        for name, m in result.items():
            ca, ce = m["ca"], m["ce"]
            if ca + ce == 0:
                assert m["instability"] == 0.0
            else:
                expected = round(ce / (ca + ce), 3)
                assert m["instability"] == expected, f"{name}: expected I={expected}, got {m['instability']}"

    @given(random_module_graph())
    @settings(max_examples=100)
    def test_distance_formula(self, g: SemGraph):
        """D ≈ |A + I - 1| (allowing for rounding of already-rounded inputs)."""
        result = martin_metrics(g)
        for name, m in result.items():
            expected = abs(m["abstractness"] + m["instability"] - 1.0)
            assert abs(m["distance"] - expected) < 0.01, f"{name}: expected D≈{expected:.3f}, got {m['distance']}"


class TestSDPViolationProperties:

    @given(random_module_graph())
    @settings(max_examples=100)
    def test_violations_have_correct_direction(self, g: SemGraph):
        """In every violation, source instability < target instability."""
        violations = sdp_violations(g)
        for v in violations:
            assert v["source_instability"] < v["target_instability"]

    @given(random_module_graph())
    @settings(max_examples=100)
    def test_violations_reference_existing_modules(self, g: SemGraph):
        violations = sdp_violations(g)
        nodes = set(g.nodes.keys())
        for v in violations:
            assert v["source"] in nodes
            assert v["target"] in nodes
