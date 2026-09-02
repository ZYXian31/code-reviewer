"""场景规则：scenario-rule（按业务场景加载的专属规则）。

场景规则完全由 config/scenarios/<场景>.json 驱动参数（命名前缀、关键词、消息、严重程度），
新增场景或调整规则无需修改核心代码。内置场景：
- general：通用场景，不加载任何场景专属规则；
- grading：批改/评分场景，要求评分相关函数以 score_/grade_ 开头。
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional

from .base import BaseRule, RuleContext, register
from ..models import Issue

_SCENARIO_SUGGESTION = "修改函数名以符合当前场景的命名约定，或在场景配置中调整规则参数"


@register("scenario-rule")  # noqa: F821
class NamingConventionRule(BaseRule):
    """命名约定规则：与场景关键词相关的函数必须使用指定前缀。

    参数（来自场景配置，均可配置）:
        required_prefixes: 必须使用的函数名前缀列表
        keywords: 判断"场景相关"的关键词（匹配函数名/文档字符串/参数名，小写包含）
        message: 输出消息模板（{prefixes} 会被替换为前缀列表）
        severity: 严重程度
    """

    name = "scenario-rule"
    category = "特定场景"
    default_severity = "warning"
    description = "违反当前业务场景加载的专属规则（参数由场景配置决定）"

    def check(self, ctx: RuleContext) -> List[Issue]:
        params = getattr(self, "params", None) or ctx.scenario_params or {}
        prefixes = [str(p) for p in params.get("required_prefixes", [])]
        keywords = [str(k).lower() for k in params.get("keywords", [])]
        message = params.get("message", "不符合当前场景的命名约定")
        if not prefixes:
            return []
        issues: List[Issue] = []

        class _Visitor(ast.NodeVisitor):
            def __init__(self, rule: NamingConventionRule, out: List[Issue]):
                self.rule = rule
                self.out = out

            def _is_related(self, node: ast.AST) -> bool:
                doc = ast.get_docstring(node, clean=False) or ""
                parts = [node.name, doc] if hasattr(node, "name") else [doc]
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    parts += [a.arg for a in node.args.args + node.args.kwonlyargs]
                    if node.args.vararg:
                        parts.append(node.args.vararg.arg)
                    if node.args.kwarg:
                        parts.append(node.args.kwarg.arg)
                for part in parts:
                    low = part.lower()
                    if any(k in low for k in keywords):
                        return True
                return False

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._check(node)
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._check(node)
                self.generic_visit(node)

            def _check(self, node: ast.AST) -> None:
                if not self._is_related(node):
                    return
                name = getattr(node, "name", "")
                if any(name.startswith(p) for p in prefixes):
                    return
                self.out.append(
                    self.rule.make_issue(
                        ctx,
                        getattr(node, "lineno", 1),
                        message.replace("{prefixes}", "/".join(prefixes)),
                        column=getattr(node, "col_offset", 0) + 1,
                        suggestion=_SCENARIO_SUGGESTION,
                    )
                )

        _Visitor(self, issues).visit(ctx.tree)
        return issues


def build_scenario_rules(scenario_config: Optional["ScenarioConfig"]) -> List[BaseRule]:
    """根据场景配置构建场景规则实例列表（配置驱动的规则工厂）。"""
    from ..config import ScenarioConfig

    rules: List[BaseRule] = []
    if not isinstance(scenario_config, ScenarioConfig):
        return rules
    for item in scenario_config.extra_rules:
        if not isinstance(item, dict):
            continue
        rule_name = item.get("rule")
        if rule_name != "scenario-rule":
            continue  # 未来可扩展其它场景规则类型
        rule = NamingConventionRule()
        params = dict(item.get("params") or {})
        params.setdefault("description", item.get("description", ""))
        if "severity" in params:
            rule.default_severity = str(params["severity"])
        rule.params = params  # type: ignore[attr-defined]
        rules.append(rule)
    return rules
