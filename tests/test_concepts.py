import pytest

from smg.concepts import Concept, ConceptConfigurationError, analyze_concepts, materialize_concepts
from smg.graph import SemGraph
from smg.model import Edge, Node, NodeType, RelType


def _node(name: str, node_type: NodeType = NodeType.MODULE) -> Node:
    return Node(name=name, type=node_type)


def _edge(source: str, target: str, rel: RelType = RelType.CONTAINS) -> Edge:
    return Edge(source=source, target=target, rel=rel)


def test_materialize_concepts_expands_prefix_anchors():
    graph = SemGraph()
    graph.add_node(_node("app", NodeType.PACKAGE))
    graph.add_node(_node("app.ui"))
    graph.add_node(_node("app.ui.render", NodeType.FUNCTION))
    graph.add_edge(_edge("app", "app.ui"))
    graph.add_edge(_edge("app.ui", "app.ui.render"))

    materialized, owners = materialize_concepts(graph, [Concept(name="ui", prefixes=["app.ui"])])

    assert len(materialized) == 1
    assert materialized[0].anchors == ["app.ui"]
    assert materialized[0].members == {"app.ui", "app.ui.render"}
    assert owners == {
        "app.ui": "ui",
        "app.ui.render": "ui",
    }


def test_materialize_concepts_rejects_overlap():
    graph = SemGraph()
    graph.add_node(_node("app", NodeType.PACKAGE))
    graph.add_node(_node("app.core"))
    graph.add_node(_node("app.core.api"))
    graph.add_node(_node("app.core.api.handle", NodeType.FUNCTION))
    graph.add_edge(_edge("app", "app.core"))
    graph.add_edge(_edge("app.core", "app.core.api"))
    graph.add_edge(_edge("app.core.api", "app.core.api.handle"))

    concepts = [
        Concept(name="api", prefixes=["app.core.api"]),
        Concept(name="core", prefixes=["app.core"]),
    ]

    with pytest.raises(ConceptConfigurationError):
        materialize_concepts(graph, concepts)


def test_analyze_concepts_reports_dependencies_and_sync_metrics():
    graph = SemGraph()
    graph.add_node(_node("app", NodeType.PACKAGE))
    graph.add_node(_node("app.ui"))
    graph.add_node(_node("app.core"))
    graph.add_node(_node("app.ui.render", NodeType.FUNCTION))
    graph.add_node(_node("app.ui.helper", NodeType.FUNCTION))
    graph.add_node(_node("app.ui.sync_port", NodeType.FUNCTION))
    graph.add_node(_node("app.core.compute", NodeType.FUNCTION))

    graph.add_edge(_edge("app", "app.ui"))
    graph.add_edge(_edge("app", "app.core"))
    graph.add_edge(_edge("app.ui", "app.ui.render"))
    graph.add_edge(_edge("app.ui", "app.ui.helper"))
    graph.add_edge(_edge("app.ui", "app.ui.sync_port"))
    graph.add_edge(_edge("app.core", "app.core.compute"))
    graph.add_edge(_edge("app.ui.render", "app.ui.helper", RelType.CALLS))
    graph.add_edge(_edge("app.ui.render", "app.core.compute", RelType.CALLS))
    graph.add_edge(_edge("app.ui.sync_port", "app.core.compute", RelType.CALLS))

    analysis = analyze_concepts(
        graph,
        [
            Concept(name="ui", prefixes=["app.ui"], sync_points=["app.ui.sync_port"]),
            Concept(name="core", prefixes=["app.core"]),
        ],
    )

    declared = {summary.name: summary for summary in analysis.declared}
    ui = declared["ui"]
    assert ui.anchors == ["app.ui"]
    assert ui.members == 4
    assert ui.internal_edges == 1
    assert ui.cross_in == 0
    assert ui.cross_out == 2
    assert ui.sync_fan_out == 1
    assert ui.sync_density == pytest.approx(2 / 3)
    assert ui.sync_asymmetry == pytest.approx(1.0)

    core = declared["core"]
    assert core.members == 2
    assert core.cross_in == 2
    assert core.cross_out == 0
    assert core.sync_density == pytest.approx(1.0)

    assert len(analysis.dependencies) == 1
    dependency = analysis.dependencies[0]
    assert dependency.source == "ui"
    assert dependency.target == "core"
    assert dependency.edge_count == 2
    assert dependency.rels == {"calls": 2}
    assert dependency.unsanctioned_count == 1
    assert dependency.unsanctioned_rels == {"calls": 1}
    assert dependency.allowed_sync is False
    assert dependency.witnesses[0]["edges"][0] == {
        "source": "app.ui.render",
        "rel": "calls",
        "target": "app.core.compute",
    }

    assert len(analysis.violations) == 1
    violation = analysis.violations[0]
    assert violation.source == "ui"
    assert violation.target == "core"
    assert violation.message == "1 unsanctioned cross-concept edge(s)"
    assert violation.rels == {"calls": 1}
    assert violation.sync_candidates == {
        "source": ["app.ui.render"],
        "target": ["app.core.compute"],
    }
    assert violation.sync_commands == {
        "source": ["smg concept sync-point ui app.ui.render"],
        "target": ["smg concept sync-point core app.core.compute"],
    }
    assert violation.witnesses[0]["edges"][0] == {
        "source": "app.ui.render",
        "rel": "calls",
        "target": "app.core.compute",
    }
