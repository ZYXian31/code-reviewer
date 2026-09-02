"""导入类规则：unused-import（导入未使用）与 prefer-orjson（性能规范）。"""

from __future__ import annotations

import ast
from typing import Dict, List, Optional, Set, Tuple

from .base import BaseRule, RuleContext, register
from ..models import Issue

_UNUSED_IMPORT_SUGGESTION = "删除未使用的导入；若为对外重导出，请使用显式 `as` 别名（如 `import x as x`）"


def _collect_root_name_loads(tree: ast.Module) -> Set[str]:
    """收集整棵 AST 中以 Load 出现的根名字（含属性链根、注解、推导式等）。"""

    class _Collector(ast.NodeVisitor):
        def __init__(self) -> None:
            self.names: Set[str] = set()

        def visit_Name(self, node: ast.Name) -> None:
            self.names.add(node.id)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            self.visit(node.value)  # 只下沉根对象

    c = _Collector()
    c.visit(tree)
    return c.names


def _iter_import_bindings(tree: ast.Module) -> List[Tuple[str, int, int, str]]:
    """返回 [(绑定名, lineno, col, 原始导入名)]，跳过 try 块内的导入（容错/回退导入模式）。"""

    class _Imports(ast.NodeVisitor):
        def __init__(self) -> None:
            self.items: List[Tuple[str, int, int, str]] = []
            self.in_try = 0

        def visit_Try(self, node: ast.Try) -> None:
            self.in_try += 1
            for stmt in node.body:
                self.visit(stmt)
            for h in node.handlers:
                for stmt in h.body:
                    self.visit(stmt)
            self.in_try -= 1
            for stmt in node.orelse + node.finalbody:
                self.visit(stmt)

        def visit_Import(self, node: ast.Import) -> None:
            if self.in_try:
                return
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                self.items.append((bound, node.lineno, node.col_offset, alias.name))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if self.in_try:
                return
            for alias in node.names:
                if alias.name == "*":
                    continue
                self.items.append(
                    (alias.asname or alias.name, node.lineno, node.col_offset, alias.name)
                )

    v = _Imports()
    v.visit(tree)
    return v.items


@register("unused-import")  # noqa: F821
class UnusedImportRule(BaseRule):
    category = "规范"
    default_severity = "info"
    description = "导入的模块/符号未被使用（注解中的引用也算使用；try 块内的容错导入不报）"

    def check(self, ctx: RuleContext) -> List[Issue]:
        assert ctx.tree is not None
        used = _collect_root_name_loads(ctx.tree)
        issues: List[Issue] = []
        seen: Set[Tuple[int, str]] = set()
        for (bound, lineno, col, orig) in _iter_import_bindings(ctx.tree):
            if bound in used:
                continue
            key = (lineno, bound)
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                self.make_issue(
                    ctx,
                    lineno,
                    f"导入的 `{bound}` 未被使用",
                    column=col + 1,
                    suggestion=_UNUSED_IMPORT_SUGGESTION,
                )
            )
        return issues


@register("prefer-orjson")  # noqa: F821
class PreferOrjsonRule(BaseRule):
    category = "性能"
    default_severity = "warning"
    description = "使用标准库 json 而非高性能的 orjson（import json / json.loads / json.dumps 均提示）"

    def check(self, ctx: RuleContext) -> List[Issue]:
        assert ctx.tree is not None
        issues: List[Issue] = []

        # 1) import json（或 import json as 别名）→ 提示
        aliases: Dict[str, str] = {}  # 本地绑定名 -> 原始名
        for (bound, lineno, col, orig) in _iter_import_bindings(ctx.tree):
            if orig.split(".")[0] == "json":
                aliases[bound] = orig
                issues.append(
                    self.make_issue(
                        ctx,
                        lineno,
                        "建议使用高性能的 orjson 替代标准库 json（import json）",
                        column=col + 1,
                        suggestion="执行 `pip install orjson`，并将 `import json` 替换为 `import orjson`",
                    )
                )

        # 2) alias.loads / alias.dumps 调用 → 提示
        class _CallVisitor(ast.NodeVisitor):
            def __init__(self, rule: PreferOrjsonRule, out: List[Issue]):
                self.rule = rule
                self.out = out

            def visit_Call(self, node: ast.Call) -> None:
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id in aliases
                    and func.attr in ("loads", "dumps")
                ):
                    self.out.append(
                        self.rule.make_issue(
                            ctx,
                            node.lineno,
                            f"建议使用 orjson.{func.attr} 替代 json.{func.attr}",
                            column=func.col_offset + 1,
                            suggestion=f"将 `json.{func.attr}` 替换为 `orjson.{func.attr}`（注意 orjson 返回值/参数类型差异）",
                        )
                    )
                self.generic_visit(node)

        _CallVisitor(self, issues).visit(ctx.tree)
        return issues
