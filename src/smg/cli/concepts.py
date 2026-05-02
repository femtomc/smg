from __future__ import annotations

import sys

import rich_click as click
from rich.table import Table

from smg.cli import EXIT_NOT_FOUND, EXIT_VALIDATION, _auto_fmt, _load, console, err_console, main


@main.group()
def concept() -> None:
    """Declare, list, and remove concept groups."""
    pass


@concept.command("add")
@click.argument("name")
@click.option(
    "--prefix",
    "prefixes",
    multiple=True,
    required=True,
    help="Package or module prefix to materialize into this concept",
)
@click.option(
    "--sync-point",
    "sync_points",
    multiple=True,
    help="Node-name prefix allowed to cross this concept boundary",
)
def concept_add(name: str, prefixes: tuple[str, ...], sync_points: tuple[str, ...]) -> None:
    """Add a concept declaration.

    \b
    Examples:
      smg concept add cli --prefix smg.cli
      smg concept add scanners --prefix smg.scan --prefix smg.langs
      smg concept add core --prefix smg.graph --prefix smg.model --sync-point smg.graph.SemGraph
    """
    from smg.concepts import Concept
    from smg.storage import load_concepts, save_concepts

    _graph, root = _load()
    concepts = load_concepts(root)
    if any(concept.name == name for concept in concepts):
        err_console.print(
            f"[red]Error:[/] concept {name!r} already exists. Remove it first with [bold]smg concept rm {name}[/]."
        )
        sys.exit(EXIT_VALIDATION)

    concepts.append(Concept(name=name, prefixes=list(prefixes), sync_points=list(sync_points)))
    save_concepts(concepts, root)
    console.print(f"Concept {name!r} added.")


@concept.command("list")
@click.option(
    "--format",
    "fmt",
    default=None,
    type=click.Choice(["text", "json"]),
    help="Output format",
)
def concept_list(fmt: str | None) -> None:
    """List all concept declarations."""
    import json as json_mod

    from smg.storage import load_concepts

    _graph, root = _load()
    concepts = load_concepts(root)
    fmt = _auto_fmt(fmt)

    if fmt == "json":
        click.echo(json_mod.dumps([concept.to_dict() for concept in concepts], indent=2))
        return

    if not concepts:
        console.print("No concepts defined. Add one with [bold]smg concept add[/].")
        return

    table = Table(show_header=True, header_style="bold", border_style="dim", pad_edge=False)
    table.add_column("Name", style="bold")
    table.add_column("Prefixes")
    table.add_column("Sync Points")
    for concept in concepts:
        sync_points = ", ".join(concept.sync_points) if concept.sync_points else "[dim]-[/]"
        table.add_row(concept.name, ", ".join(concept.prefixes), sync_points)
    console.print(table)


@concept.command("sync-point")
@click.argument("name")
@click.argument("sync_point")
def concept_sync_point(name: str, sync_point: str) -> None:
    """Add a sync-point prefix to an existing concept declaration.

    \b
    Example:
      smg concept sync-point core app.core.public_api
    """
    from smg.storage import load_concepts, save_concepts

    _graph, root = _load()
    concepts = load_concepts(root)
    for concept_obj in concepts:
        if concept_obj.name != name:
            continue
        if sync_point not in concept_obj.sync_points:
            concept_obj.sync_points.append(sync_point)
            concept_obj.sync_points = sorted(set(concept_obj.sync_points))
            save_concepts(concepts, root)
            console.print(f"Concept {name!r} sync point added.")
        else:
            console.print(f"Concept {name!r} already has that sync point.")
        return

    err_console.print(f"[red]Error:[/] concept {name!r} not found.")
    sys.exit(EXIT_NOT_FOUND)


@concept.command("rm")
@click.argument("name")
def concept_rm(name: str) -> None:
    """Remove a concept declaration by name."""
    from smg.storage import load_concepts, save_concepts

    _graph, root = _load()
    concepts = load_concepts(root)
    new_concepts = [concept for concept in concepts if concept.name != name]
    if len(new_concepts) == len(concepts):
        err_console.print(f"[red]Error:[/] concept {name!r} not found.")
        sys.exit(EXIT_NOT_FOUND)
    save_concepts(new_concepts, root)
    console.print(f"Concept {name!r} removed.")
