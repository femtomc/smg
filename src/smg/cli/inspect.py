from __future__ import annotations

import sys

import rich_click as click

from smg import export, query
from smg.cli import (
    _DEFAULT_LIMIT,
    EXIT_NOT_FOUND,
    EXIT_VALIDATION,
    _auto_fmt,
    _load,
    _output_edges,
    _output_graph,
    _output_names,
    _resolve_or_exit,
    _type_badge,
    console,
    err_console,
    main,
)
from smg.graph import SemGraph


@main.command()
@click.argument("name")
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["text", "json"]),
    hidden=True,
    help="Output format (hidden, use --json instead)",
)
@click.option("--json", "use_json", is_flag=True, help="Emit JSON detail")
@click.option("--full", is_flag=True, help="Show all edges (no truncation)")
def show(name: str, fmt: str | None, use_json: bool, full: bool) -> None:
    """Show a node's details, connections, and metrics.

    Short names work: [bold]smg show SemGraph[/] resolves if unambiguous.
    Functions/methods include cyclomatic complexity, fan-in/fan-out, etc.
    """
    graph, _root = _load()
    name = _resolve_or_exit(graph, name)
    node = graph.get_node(name)
    assert node is not None
    inc = graph.incoming(name)
    out = graph.outgoing(name)

    effective_json = use_json or (fmt == "json" if fmt else False)
    if effective_json:
        click.echo(export.format_node(node, inc, out, fmt="json"))
        return

    edge_limit = 0 if full else _DEFAULT_LIMIT

    # Plain text record view (no box-drawing, no ANSI, identical in TTY and pipe)
    click.echo(f"{node.name}  [{node.type.value}]")
    if node.file:
        loc = node.file
        if node.line is not None:
            loc += f":{node.line}"
            if node.end_line is not None and node.end_line != node.line:
                loc += f"-{node.end_line}"
        click.echo(f"file:  {loc}")
    if node.docstring:
        doc = node.docstring.split("\n")[0]
        click.echo(f"doc:   {doc}")
    if node.metadata:
        for k, v in sorted(node.metadata.items()):
            click.echo(f"{k}:  {v}")

    if inc:
        click.echo("")
        click.echo(f"Incoming ({len(inc)})")
        show_inc = inc if edge_limit == 0 else inc[:edge_limit]
        for e in show_inc:
            click.echo(f"  {e.source} --{e.rel.value}--> {node.name}")
        if edge_limit and len(inc) > edge_limit:
            click.echo(f"  ... and {len(inc) - edge_limit} more (use --full)")

    if out:
        click.echo("")
        click.echo(f"Outgoing ({len(out)})")
        show_out = out if edge_limit == 0 else out[:edge_limit]
        for e in show_out:
            click.echo(f"  {node.name} --{e.rel.value}--> {e.target}")
        if edge_limit and len(out) > edge_limit:
            click.echo(f"  ... and {len(out) - edge_limit} more (use --full)")


@main.command("list")
@click.option("--type", "type_", default=None, help="Filter by node type")
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["text", "json"]),
    hidden=True,
    help="Output format (hidden, use --json instead)",
)
@click.option("--json", "use_json", is_flag=True, help="Emit canonical JSON envelope")
@click.option("--json-legacy", "json_legacy", is_flag=True, hidden=True, help="Emit bare JSON array (legacy)")
@click.option("--limit", "limit_", default=_DEFAULT_LIMIT, type=int, help="Max rows (0 = unlimited, default 20)")
@click.option("--full", is_flag=True, help="Show expanded detail per node")
def list_nodes(type_: str | None, fmt: str | None, use_json: bool, json_legacy: bool, limit_: int, full: bool) -> None:
    """List all nodes in the graph.

    \b
    Filter by type: smg list --type class
    Valid types: package, module, class, function, method, interface,
                 variable, constant, type, endpoint, config
    """
    import json as json_mod

    from smg.cli._compact import compact_json_envelope, compact_table

    graph, _root = _load()
    nodes = graph.all_nodes(type=type_)
    effective_json = use_json or fmt == "json"

    if json_legacy:
        data = [n.to_dict() for n in nodes]
        for d in data:
            d.pop("kind", None)
        click.echo(json_mod.dumps(data, indent=2))
        return

    total = len(nodes)
    display = nodes if limit_ == 0 else nodes[:limit_]

    list_columns: list[tuple[str, str, dict]] = [
        ("type", "type", {"max_width": 12}),
        ("name", "name", {"max_width": 40}),
        ("file", "file", {"max_width": 40}),
    ]

    rows: list[dict[str, object]] = []
    for node in display:
        loc = ""
        if node.file:
            loc = node.file
            if node.line is not None:
                loc += f":{node.line}"
                if node.end_line is not None and node.end_line != node.line:
                    loc += f"-{node.end_line}"
        rows.append({"type": node.type.value, "name": node.name, "file": loc})

    if effective_json:
        envelope = compact_json_envelope(rows, list_columns, total=total, limit=limit_)
        click.echo(json_mod.dumps(envelope, indent=2))
        return

    if not nodes:
        click.echo("No nodes.")
        return

    displayed_total = total if total > len(rows) else None
    click.echo(compact_table(rows, list_columns, total=displayed_total))


@main.command()
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["text", "json"]),
    hidden=True,
    help="Output format (hidden, use --json instead)",
)
@click.option("--json", "use_json", is_flag=True, help="Emit JSON summary")
@click.option("--full", is_flag=True, help="Expanded detail")
def status(fmt: str | None, use_json: bool, full: bool) -> None:
    """Show graph summary — node/edge counts broken down by type."""
    import json as json_mod

    from smg.cli._compact import compact_table

    graph, _root = _load()
    nodes = graph.all_nodes()
    edges = graph.all_edges()
    effective_json = use_json or (fmt == "json" if fmt else False)

    type_counts: dict[str, int] = {}
    for n in nodes:
        type_counts[n.type.value] = type_counts.get(n.type.value, 0) + 1
    rel_counts: dict[str, int] = {}
    for e in edges:
        rel_counts[e.rel.value] = rel_counts.get(e.rel.value, 0) + 1

    if effective_json:
        data = {
            "nodes": len(nodes),
            "edges": len(edges),
            "node_types": type_counts,
            "rel_types": rel_counts,
        }
        click.echo(json_mod.dumps(data, indent=2))
        return

    node_cols: list[tuple[str, str, dict]] = [
        ("type", "type", {}),
        ("count", "count", {"align": "right"}),
    ]
    edge_cols: list[tuple[str, str, dict]] = [
        ("relationship", "relationship", {}),
        ("count", "count", {"align": "right"}),
    ]
    node_rows = [{"type": t, "count": str(c)} for t, c in sorted(type_counts.items())]
    edge_rows = [{"relationship": r, "count": str(c)} for r, c in sorted(rel_counts.items())]

    click.echo(f"Nodes ({len(nodes)})")
    click.echo(compact_table(node_rows, node_cols))
    click.echo()
    click.echo(f"Edges ({len(edges)})")
    click.echo(compact_table(edge_rows, edge_cols))


# --- Query subgroup ---


@main.group()
def query_cmd() -> None:
    """Low-level graph queries — deps, callers, paths, subgraphs, edges.

    For high-level questions, try [bold]about[/], [bold]impact[/], or [bold]between[/] instead.
    """
    pass


main.add_command(query_cmd, "query")


@query_cmd.command("deps")
@click.argument("name")
@click.option("--depth", default=None, type=int, help="Max traversal depth")
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["text", "json", "mermaid", "dot"]),
    help="Output format",
)
@click.option("--limit", "limit_", default=_DEFAULT_LIMIT, type=int, help="Max rows (0 = unlimited, default 20)")
def query_deps(name: str, depth: int | None, fmt: str | None, limit_: int) -> None:
    """Transitive dependencies of a node (follows imports/depends_on edges)."""
    graph, _root = _load()
    name = _resolve_or_exit(graph, name)
    fmt = _auto_fmt(fmt)
    deps = query.transitive_deps(graph, name, max_depth=depth)
    _output_names(deps, f"Dependencies of {name}", fmt, graph, name, limit=limit_)


@query_cmd.command("callers")
@click.argument("name")
@click.option("--depth", default=None, type=int, help="Max traversal depth")
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["text", "json", "mermaid", "dot"]),
    help="Output format",
)
@click.option("--limit", "limit_", default=_DEFAULT_LIMIT, type=int, help="Max rows (0 = unlimited, default 20)")
def query_callers(name: str, depth: int | None, fmt: str | None, limit_: int) -> None:
    """What calls this node (transitively, follows incoming calls edges)."""
    graph, _root = _load()
    name = _resolve_or_exit(graph, name)
    fmt = _auto_fmt(fmt)
    callers = query.transitive_callers(graph, name, max_depth=depth)
    _output_names(callers, f"Callers of {name}", fmt, graph, name, limit=limit_)


@query_cmd.command("path")
@click.argument("source")
@click.argument("target")
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["text", "json"]),
    help="Output format",
)
def query_path(source: str, target: str, fmt: str | None) -> None:
    """Shortest path between two nodes."""
    graph, _root = _load()
    source = _resolve_or_exit(graph, source)
    target = _resolve_or_exit(graph, target)
    fmt = _auto_fmt(fmt)
    path = query.shortest_path(graph, source, target)
    if path is None:
        err_console.print(f"[red]Error:[/] no path from {source} to {target}")
        sys.exit(EXIT_NOT_FOUND)
    if fmt == "json":
        import json

        click.echo(json.dumps(path))
    else:
        styled = " [dim]->[/] ".join(f"[bold]{p}[/]" for p in path)
        console.print(styled)


@query_cmd.command("subgraph")
@click.argument("name")
@click.option("--depth", default=2, type=int, help="Number of hops [dim](default: 2)[/]")
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["text", "json", "mermaid", "dot"]),
    help="Output format",
)
@click.option("--full", is_flag=True, help="Dump full subgraph (no summary)")
@click.option("--limit", "limit_", default=None, type=int, help="Max nodes (default 10; 50 with --full; 0 = unlimited)")
def query_subgraph(name: str, depth: int, fmt: str | None, full: bool, limit_: int | None) -> None:
    """Neighborhood around a node."""
    graph, _root = _load()
    name = _resolve_or_exit(graph, name)
    fmt = _auto_fmt(fmt)
    sub = query.subgraph(graph, name, depth=depth)

    if fmt != "text":
        _output_graph(sub, fmt)
        return

    sub_nodes = sub.all_nodes()
    sub_edges = sub.all_edges()

    if full:
        cap = limit_ if limit_ is not None else 50
        if cap > 0 and len(sub_nodes) > cap:
            degrees = sorted(
                ((n, len(sub.incoming(n.name)) + len(sub.outgoing(n.name))) for n in sub_nodes),
                key=lambda x: x[1],
                reverse=True,
            )
            keep = {n.name for n, _ in degrees[:cap]}
            pruned = SemGraph()
            for n, _ in degrees[:cap]:
                pruned.add_node(n)
            for e in sub.all_edges():
                if e.source in keep and e.target in keep:
                    pruned.add_edge(e)
            _output_graph(pruned, "text")
            click.echo(f"(showing {cap} of {len(sub_nodes)} nodes -- use --limit 0 for all)")
        else:
            _output_graph(sub, "text")
        return

    # Compact text summary (top N by degree)
    effective_limit = limit_ if limit_ is not None else 10
    console.print(f"[bold]Subgraph of[/] {name} [dim](depth={depth})[/]")
    console.print(f"  {len(sub_nodes)} nodes, {len(sub_edges)} edges\n")

    degrees_list: list[tuple[str, int]] = []
    for n in sub_nodes:
        d = len(sub.incoming(n.name)) + len(sub.outgoing(n.name))
        degrees_list.append((n.name, d))
    degrees_list.sort(key=lambda x: x[1], reverse=True)

    cap = effective_limit if effective_limit > 0 else len(degrees_list)
    for node_name, deg in degrees_list[:cap]:
        n = sub.get_node(node_name)
        t = n.type.value if n else "?"
        console.print(f"  [{_type_badge(t)}] {node_name} [dim]({deg} edges)[/]")
    if cap < len(degrees_list):
        console.print(f"  [dim]... and {len(degrees_list) - cap} more (use --full or --limit 0)[/]")


@query_cmd.command("incoming")
@click.argument("name")
@click.option("--rel", default=None, help="Filter by relationship type")
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["text", "json"]),
    help="Output format",
)
@click.option("--limit", "limit_", default=_DEFAULT_LIMIT, type=int, help="Max rows (0 = unlimited, default 20)")
def query_incoming(name: str, rel: str | None, fmt: str | None, limit_: int) -> None:
    """Incoming edges to a node. Filter with --rel calls, --rel imports, etc."""
    graph, _root = _load()
    name = _resolve_or_exit(graph, name)
    fmt = _auto_fmt(fmt)
    edges = graph.incoming(name, rel=rel)
    _output_edges(edges, fmt, limit=limit_)


@query_cmd.command("outgoing")
@click.argument("name")
@click.option("--rel", default=None, help="Filter by relationship type")
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["text", "json"]),
    help="Output format",
)
@click.option("--limit", "limit_", default=_DEFAULT_LIMIT, type=int, help="Max rows (0 = unlimited, default 20)")
def query_outgoing(name: str, rel: str | None, fmt: str | None, limit_: int) -> None:
    """Outgoing edges from a node. Filter with --rel calls, --rel imports, etc."""
    graph, _root = _load()
    name = _resolve_or_exit(graph, name)
    fmt = _auto_fmt(fmt)
    edges = graph.outgoing(name, rel=rel)
    _output_edges(edges, fmt, limit=limit_)


# --- Validate ---


@main.command()
def validate() -> None:
    """Check graph integrity (dangling edges, missing nodes)."""
    graph, _root = _load()
    issues = graph.validate()
    if not issues:
        console.print("[green]Graph is valid.[/]")
    else:
        err_console.print(f"[red]Found {len(issues)} issue(s):[/]")
        for issue in issues:
            err_console.print(f"  [dim]-[/] {issue}")
        sys.exit(EXIT_VALIDATION)
