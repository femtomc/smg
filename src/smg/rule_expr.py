"""Parse and evaluate quantified rule assertions safely."""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Any, Mapping

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_ALLOWED_CMPOPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_ALLOWED_UNARYOPS = {
    ast.Not: operator.not_,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_ALLOWED_CONSTANT_TYPES = (bool, int, float, str)


@dataclass(frozen=True)
class ParsedAssertion:
    """Validated representation of one quantified assertion."""

    source: str
    tree: ast.expr
    identifiers: frozenset[str]


def parse_assertion(source: str) -> ParsedAssertion:
    """Parse and validate a quantified rule assertion."""
    try:
        parsed = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid assertion: {source!r}") from exc
    identifiers: set[str] = set()
    _validate_expr(parsed.body, identifiers)
    return ParsedAssertion(source=source, tree=parsed.body, identifiers=frozenset(identifiers))


def evaluate_assertion(assertion: ParsedAssertion, facts: Mapping[str, Any]) -> Any:
    """Evaluate a parsed assertion against a metric bag."""
    return _eval_expr(assertion.tree, facts)


def _validate_expr(node: ast.AST, identifiers: set[str]) -> None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, _ALLOWED_CONSTANT_TYPES):
            return
        raise ValueError(f"unsupported literal in assertion: {node.value!r}")
    if isinstance(node, ast.Name):
        identifiers.add(node.id)
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _ALLOWED_UNARYOPS:
            raise ValueError(f"unsupported unary operator in assertion: {ast.dump(node.op)}")
        _validate_expr(node.operand, identifiers)
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _ALLOWED_BINOPS:
            raise ValueError(f"unsupported arithmetic operator in assertion: {ast.dump(node.op)}")
        _validate_expr(node.left, identifiers)
        _validate_expr(node.right, identifiers)
        return
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise ValueError(f"unsupported boolean operator in assertion: {ast.dump(node.op)}")
        for value in node.values:
            _validate_expr(value, identifiers)
        return
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("chained comparisons are not supported in quantified assertions")
        if type(node.ops[0]) not in _ALLOWED_CMPOPS:
            raise ValueError(f"unsupported comparison operator in assertion: {ast.dump(node.ops[0])}")
        _validate_expr(node.left, identifiers)
        _validate_expr(node.comparators[0], identifiers)
        return
    raise ValueError(f"unsupported syntax in assertion: {ast.dump(node)}")


def _eval_expr(node: ast.AST, facts: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in facts:
            raise KeyError(node.id)
        return facts[node.id]
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARYOPS[type(node.op)]
        return op(_eval_expr(node.operand, facts))
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BINOPS[type(node.op)]
        return op(_eval_expr(node.left, facts), _eval_expr(node.right, facts))
    if isinstance(node, ast.BoolOp):
        values = [_eval_expr(value, facts) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(bool(value) for value in values)
        return any(bool(value) for value in values)
    if isinstance(node, ast.Compare):
        op = _ALLOWED_CMPOPS[type(node.ops[0])]
        return op(_eval_expr(node.left, facts), _eval_expr(node.comparators[0], facts))
    raise ValueError(f"unsupported syntax in assertion: {ast.dump(node)}")
