"""Regression tests: AST walks must be iterative (no RecursionError).

Commit 3777b9d converted all recursive AST walks to iterative (explicit
stack). These tests build synthetically deep ASTs and exercise the walkers
under a reduced recursion limit to ensure the iterative invariant holds.
"""

import sys
import textwrap

import pytest

try:
    import tree_sitter_python as tsp
    from tree_sitter import Language, Parser

    PY_LANG = Language(tsp.language())
    PY_PARSER = Parser(PY_LANG)
    HAS_PYTHON = True
except ImportError:
    HAS_PYTHON = False

try:
    import tree_sitter_c as tsc
    from tree_sitter import Language, Parser

    C_LANG = Language(tsc.language())
    C_PARSER = Parser(C_LANG)
    HAS_C = True
except ImportError:
    HAS_C = False

needs_python = pytest.mark.skipif(not HAS_PYTHON, reason="tree-sitter-python not installed")
needs_c = pytest.mark.skipif(not HAS_C, reason="tree-sitter-c not installed")

DEPTH = 500
"""Nesting depth for synthetic ASTs.  Under the default recursion limit of
1000, a recursive walker would overflow well before reaching this depth
(each level uses several Python frames).  The iterative walkers handle it
with no issue."""

LOW_LIMIT = 200
"""Recursion limit set during test execution.  Any surviving recursive call
deeper than ~200 frames will raise RecursionError."""


def _deeply_nested_python(depth: int) -> str:
    """Generate a Python function with ``depth`` nested if-statements."""
    lines = ["def deep(x):"]
    for i in range(depth):
        indent = "    " * (i + 1)
        lines.append(f"{indent}if x > {i}:")
    # Innermost body
    lines.append("    " * (depth + 1) + "return x")
    return "\n".join(lines) + "\n"


def _deeply_nested_c(depth: int) -> str:
    """Generate a C function with ``depth`` nested if-statements."""
    lines = ["void deep(int x) {"]
    for i in range(depth):
        indent = "    " * (i + 1)
        lines.append(f"{indent}if (x > {i}) {{")
    # Innermost body
    lines.append("    " * (depth + 1) + "x = 0;")
    # Close all braces
    for i in range(depth - 1, -1, -1):
        indent = "    " * (i + 1)
        lines.append(f"{indent}}}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _py_func_node(code: str):
    tree = PY_PARSER.parse(code.encode())
    for child in tree.root_node.children:
        if child.type == "function_definition":
            return child
    raise ValueError("No function_definition found")


def _c_func_node(code: str):
    tree = C_PARSER.parse(code.encode())
    for child in tree.root_node.children:
        if child.type == "function_definition":
            return child
    raise ValueError("No function_definition found")


# --- Python metrics walkers ---


@needs_python
def test_walk_for_metrics_deep_python():
    """_walk_for_metrics handles deeply nested ASTs without recursion."""
    from smg.metrics import PYTHON_BRANCH_MAP, compute_metrics

    code = _deeply_nested_python(DEPTH)
    node = _py_func_node(code)

    old_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(LOW_LIMIT)
        m = compute_metrics(node, PYTHON_BRANCH_MAP)
    finally:
        sys.setrecursionlimit(old_limit)

    # Each nested if adds 1 to CC
    assert m.cyclomatic_complexity == 1 + DEPTH
    assert m.max_nesting_depth == DEPTH
    assert m.return_count == 1


@needs_python
def test_walk_fused_deep_python():
    """_walk_fused (metrics + structure hash) handles deep ASTs without recursion."""
    from smg.metrics import PYTHON_BRANCH_MAP, compute_metrics_and_hash

    code = _deeply_nested_python(DEPTH)
    node = _py_func_node(code)

    old_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(LOW_LIMIT)
        meta = compute_metrics_and_hash(node, PYTHON_BRANCH_MAP)
    finally:
        sys.setrecursionlimit(old_limit)

    assert meta.metrics.cyclomatic_complexity == 1 + DEPTH
    assert meta.metrics.max_nesting_depth == DEPTH
    assert meta.metrics.return_count == 1
    assert len(meta.structure_hash) > 0


@needs_python
def test_structure_hash_deep_python():
    """compute_structure_hash handles deep ASTs without recursion."""
    from smg.metrics import compute_structure_hash

    code = _deeply_nested_python(DEPTH)
    node = _py_func_node(code)

    old_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(LOW_LIMIT)
        h = compute_structure_hash(node)
    finally:
        sys.setrecursionlimit(old_limit)

    assert len(h) > 0


# --- C metrics walkers ---


@needs_c
def test_walk_for_metrics_deep_c():
    """_walk_for_metrics handles deeply nested C ASTs without recursion."""
    from smg.langs.c import C_BRANCH_MAP
    from smg.metrics import compute_metrics

    code = _deeply_nested_c(DEPTH)
    node = _c_func_node(code)

    old_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(LOW_LIMIT)
        m = compute_metrics(node, C_BRANCH_MAP)
    finally:
        sys.setrecursionlimit(old_limit)

    assert m.cyclomatic_complexity == 1 + DEPTH
    assert m.max_nesting_depth == DEPTH


@needs_c
def test_walk_fused_deep_c():
    """_walk_fused handles deeply nested C ASTs without recursion."""
    from smg.langs.c import C_BRANCH_MAP
    from smg.metrics import compute_metrics_and_hash

    code = _deeply_nested_c(DEPTH)
    node = _c_func_node(code)

    old_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(LOW_LIMIT)
        meta = compute_metrics_and_hash(node, C_BRANCH_MAP)
    finally:
        sys.setrecursionlimit(old_limit)

    assert meta.metrics.cyclomatic_complexity == 1 + DEPTH
    assert meta.metrics.max_nesting_depth == DEPTH
    assert len(meta.structure_hash) > 0


# --- C extractor call extraction ---


@needs_c
def test_extract_calls_deep_c():
    """_extract_calls handles deeply nested C ASTs without recursion."""
    from smg.langs.c import CExtractor

    # Deeply nested code with a function call at the bottom
    lines = ["void deep(int x) {"]
    for i in range(DEPTH):
        indent = "    " * (i + 1)
        lines.append(f"{indent}if (x > {i}) {{")
    lines.append("    " * (DEPTH + 1) + "helper();")
    for i in range(DEPTH - 1, -1, -1):
        indent = "    " * (i + 1)
        lines.append(f"{indent}}}")
    lines.append("}")
    code = "\n".join(lines) + "\n"

    ext = CExtractor()
    old_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(LOW_LIMIT)
        result = ext.extract(code.encode(), "deep.c", "deep")
    finally:
        sys.setrecursionlimit(old_limit)

    # Should have extracted the function and found the call
    func_nodes = [n for n in result.nodes if n.name == "deep.deep"]
    assert len(func_nodes) == 1
    call_edges = [e for e in result.edges if e.target == "helper"]
    assert len(call_edges) == 1


# --- Determinism: iterative produces same results as expected ---


@needs_python
def test_iterative_matches_expected_python():
    """Iterative walkers produce correct results on moderate nesting."""
    from smg.metrics import PYTHON_BRANCH_MAP, compute_metrics, compute_metrics_and_hash

    code = textwrap.dedent("""\
        def f(x, y):
            if x > 0:
                for i in range(y):
                    if i > 5:
                        return i
            return 0
    """)
    node = _py_func_node(code)

    m1 = compute_metrics(node, PYTHON_BRANCH_MAP)
    m2 = compute_metrics_and_hash(node, PYTHON_BRANCH_MAP)

    # Both paths should agree on metrics
    assert m1.cyclomatic_complexity == m2.metrics.cyclomatic_complexity
    assert m1.cognitive_complexity == m2.metrics.cognitive_complexity
    assert m1.max_nesting_depth == m2.metrics.max_nesting_depth
    assert m1.return_count == m2.metrics.return_count

    # Spot-check values
    assert m1.cyclomatic_complexity == 4  # 1 + if + for + if
    assert m1.max_nesting_depth == 3
    assert m1.return_count == 2
