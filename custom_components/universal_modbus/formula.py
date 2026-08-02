"""Safe evaluation of per-entity calculation formulas."""

from __future__ import annotations

import ast
from functools import lru_cache
from typing import Any


DEFAULT_READ_FORMULA = "register_value * scale + offset"
DEFAULT_WRITE_FORMULA = "(value - offset) / scale"

_FUNCTIONS = {
    "abs": abs,
    "bool": bool,
    "float": float,
    "int": int,
    "max": max,
    "min": min,
    "round": round,
}
_ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
)
_MAX_FORMULA_LENGTH = 500
_MAX_AST_NODES = 100


class FormulaError(ValueError):
    """Raised when a calculation formula is invalid or cannot be evaluated."""


@lru_cache(maxsize=256)
def _compile_formula(expression: str, variable: str):
    if not isinstance(expression, str):
        raise FormulaError("Formula must be text")
    expression = expression.strip()
    if not expression:
        raise FormulaError("Formula must not be empty")
    if len(expression) > _MAX_FORMULA_LENGTH:
        raise FormulaError("Formula is too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as err:
        raise FormulaError(f"Invalid formula syntax: {err.msg}") from err

    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_AST_NODES:
        raise FormulaError("Formula is too complex")
    allowed_names = {variable, "scale", "offset", *_FUNCTIONS}
    for node in nodes:
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaError(f"Unsupported formula element: {type(node).__name__}")
        if isinstance(node, ast.Constant) and not (
            node.value is None or isinstance(node.value, (bool, int, float))
        ):
            raise FormulaError("Only numeric, boolean, and None constants are allowed")
        if isinstance(node, ast.Name) and node.id not in allowed_names:
            raise FormulaError(f"Unknown formula name: {node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
                raise FormulaError("Unsupported formula function")
            if node.keywords or len(node.args) > 10:
                raise FormulaError("Formula functions only accept positional arguments")

    return compile(tree, "<modbus-formula>", "eval")


def validate_formula(expression: str, variable: str) -> None:
    """Validate a read or write formula without evaluating it."""
    if variable not in {"register_value", "value"}:
        raise ValueError(f"Unsupported formula variable: {variable}")
    _compile_formula(expression, variable)


def evaluate_formula(
    expression: str,
    variable: str,
    value: Any,
    *,
    scale: float,
    offset: float,
) -> Any:
    """Evaluate a validated formula in a restricted environment."""
    code = _compile_formula(expression, variable)
    environment = {
        **_FUNCTIONS,
        variable: value,
        "scale": scale,
        "offset": offset,
    }
    try:
        result = eval(code, {"__builtins__": {}}, environment)  # noqa: S307
    except Exception as err:
        raise FormulaError(f"Formula evaluation failed: {err}") from err
    if result is not None and not isinstance(result, (bool, int, float)):
        raise FormulaError("Formula result must be numeric, boolean, or None")
    return result
