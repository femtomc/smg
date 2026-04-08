from __future__ import annotations

from collections import deque

from smg.graph import SemGraph
from smg.model import RelType

COUPLING_RELS = frozenset(
    {
        RelType.CALLS.value,
        RelType.IMPORTS.value,
        RelType.INHERITS.value,
        RelType.IMPLEMENTS.value,
        RelType.DEPENDS_ON.value,
    }
)


def transitive_deps(
    graph: SemGraph,
    name: str,
    rel_types: set[str] | None = None,
    max_depth: int | None = None,
) -> list[str]:
    """BFS following outgoing edges of given rel_types. Default: depends_on, imports."""
    if rel_types is None:
        rel_types = {RelType.DEPENDS_ON.value, RelType.IMPORTS.value}
    return _bfs_outgoing(graph, name, rel_types, max_depth)


def transitive_callers(
    graph: SemGraph,
    name: str,
    max_depth: int | None = None,
) -> list[str]:
    """Follow incoming 'calls' edges transitively."""
    return _bfs_incoming(graph, name, {RelType.CALLS.value}, max_depth)


def shortest_path(graph: SemGraph, source: str, target: str) -> list[str] | None:
    """BFS shortest path (undirected — follows edges in both directions)."""
    if source not in graph.nodes or target not in graph.nodes:
        return None
    if source == target:
        return [source]

    visited: set[str] = {source}
    queue: deque[list[str]] = deque([[source]])

    while queue:
        path = queue.popleft()
        current = path[-1]
        for neighbor in graph.iter_neighbors(current, direction="both"):
            if neighbor == target:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])

    return None


def subgraph(
    graph: SemGraph,
    name: str,
    depth: int = 2,
    direction: str = "both",
    rel_types: set[str] | None = None,
) -> SemGraph:
    """Return a new SemGraph containing nodes within `depth` hops of `name`."""
    if name not in graph.nodes:
        return SemGraph()

    visited: set[str] = {name}
    frontier: set[str] = {name}

    for _ in range(depth):
        next_frontier: set[str] = set()
        for node_name in frontier:
            for neighbor in _iter_neighbors(graph, node_name, direction=direction, rel_types=rel_types):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break

    # Build new graph with discovered nodes and edges between them
    sub = SemGraph()
    for n in visited:
        node = graph.get_node(n)
        if node is not None:
            sub.add_node(node)

    for edge in graph.iter_edges(rel_types=rel_types):
        if edge.source in visited and edge.target in visited:
            sub.add_edge(edge)

    return sub


def impact(
    graph: SemGraph,
    name: str,
    rel_types: set[str] | None = None,
    max_depth: int | None = None,
) -> list[str]:
    """All nodes reachable via incoming edges of any type (reverse transitive closure)."""
    visited: set[str] = {name}
    queue: deque[tuple[str, int]] = deque([(name, 0)])

    while queue:
        current, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            continue
        for edge in graph.iter_incoming(current):
            if rel_types is not None and edge.rel.value not in rel_types:
                continue
            if edge.source not in visited:
                visited.add(edge.source)
                queue.append((edge.source, depth + 1))

    return sorted(visited - {name})


def containment_path(graph: SemGraph, name: str) -> list[str]:
    """Walk up the containment chain: [root_package, ..., parent, name]."""
    path = [name]
    current = name
    while True:
        parent = next(
            (edge.source for edge in graph.iter_incoming(current, rel=RelType.CONTAINS)),
            None,
        )
        if parent is None:
            break
        current = parent
        path.append(current)
    path.reverse()
    return path


def ancestors(
    graph: SemGraph,
    name: str,
    rel: str,
    max_depth: int | None = None,
) -> list[str]:
    """Transitive incoming edges of a given type."""
    return _bfs_incoming(graph, name, {rel}, max_depth)


def descendants(
    graph: SemGraph,
    name: str,
    rel: str,
    max_depth: int | None = None,
) -> list[str]:
    """Transitive outgoing edges of a given type."""
    return _bfs_outgoing(graph, name, {rel}, max_depth)


def _bfs_outgoing(
    graph: SemGraph,
    start: str,
    rel_types: set[str],
    max_depth: int | None,
) -> list[str]:
    visited: set[str] = {start}
    queue: deque[tuple[str, int]] = deque([(start, 0)])

    while queue:
        current, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            continue
        for edge in graph.iter_outgoing(current):
            if edge.rel.value in rel_types and edge.target not in visited:
                visited.add(edge.target)
                queue.append((edge.target, depth + 1))

    return sorted(visited - {start})


def _bfs_incoming(
    graph: SemGraph,
    start: str,
    rel_types: set[str],
    max_depth: int | None,
) -> list[str]:
    visited: set[str] = {start}
    queue: deque[tuple[str, int]] = deque([(start, 0)])

    while queue:
        current, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            continue
        for edge in graph.iter_incoming(current):
            if edge.rel.value in rel_types and edge.source not in visited:
                visited.add(edge.source)
                queue.append((edge.source, depth + 1))

    return sorted(visited - {start})


def _iter_neighbors(
    graph: SemGraph,
    name: str,
    direction: str,
    rel_types: set[str] | None,
):
    if rel_types is None:
        yield from graph.iter_neighbors(name, direction=direction)
        return

    if direction in ("out", "both"):
        for edge in graph.iter_outgoing(name):
            if edge.rel.value in rel_types:
                yield edge.target

    if direction in ("in", "both"):
        seen: set[str] = set()
        if direction == "both":
            seen.update(edge.target for edge in graph.iter_outgoing(name) if edge.rel.value in rel_types)
        for edge in graph.iter_incoming(name):
            if edge.rel.value in rel_types and edge.source not in seen:
                yield edge.source
