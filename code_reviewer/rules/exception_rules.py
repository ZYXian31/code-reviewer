"""异常类规则：bare-except（裸 except 未指定异常类型）。"""

from __future__ import annotations

import ast
from typing import List

from .base import BaseRule, RuleContext, register
from ..models import Issue

_BARE_EXCEPT_SUGGESTION = "请指定具体的异常类型，如 `except ValueError:`、`except (ValueError, TypeError):` 或 `except Exception as e:`"


@register("bare-except")  # noqa: F821
class BareExceptRule(BaseRule):
    category = "规范"
    default_severity = "warning"
    description = "使用裸 except: 未指定异常类型（会捕获包括 KeyboardInterrupt/SystemExit 在内的所有异常）"

    def check(self, ctx: RuleContext) -> List[Issue]:
        assert ctx.tree is not None
        issues: List[Issue] = []

        class _Visitor(ast.NodeVisitor):
            def __init__(self, rule: BareExceptRule, out: List[Issue]):
                self.rule = rule
                self.out = out

            def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
                if node.type is None:
                    self.out.append(
                        self.rule.make_issue(
                            ctx,
                            node.lineno,
                            "建议指定捕获的异常类型",
                            column=node.col_offset + 1,
                            suggestion=_BARE_EXCEPT_SUGGESTION,
                        )
                    )
                self.generic_visit(node)

        _Visitor(self, issues).visit(ctx.tree)
        return issues
