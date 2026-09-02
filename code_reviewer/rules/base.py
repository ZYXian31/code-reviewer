"""规则基类与规则注册表。

新增规则三步（无需修改核心代码）：
1. 继承 BaseRule 实现 check()；
2. 用 @register("rule-name") 装饰器注册；
3. 在 config/rules.json 中配置 enabled / severity。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models import Issue, RuleMeta


@dataclass
class RuleContext:
    """规则执行上下文：源码、AST、场景配置等。"""

    source: str
    lines: List[str]
    tree: Optional[Any]  # ast.Module，解析成功时非空
    parse_error: Optional[Exception] = None
    scenario: str = "general"
    scenario_params: Optional[Dict[str, Any]] = None  # 场景专属规则参数
    config: Optional[Dict[str, Any]] = None  # 规则自身参数

    def line_text(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].rstrip("\n")
        return ""


class BaseRule:
    """所有规则的基类。子类需定义 name/category/default_severity/description 并实现 check()。"""

    name: str = ""
    category: str = ""
    default_severity: str = "warning"
    description: str = ""
    enabled: bool = True

    def check(self, ctx: RuleContext) -> List[Issue]:  # pragma: no cover - 抽象方法
        raise NotImplementedError

    def make_issue(
        self,
        ctx: RuleContext,
        lineno: int,
        message: str,
        column: int = 1,
        suggestion: str = "",
        rule: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> Issue:
        return Issue(
            rule=rule or self.name,
            severity=severity or self.default_severity,
            line=lineno,
            column=column,
            message=message,
            suggestion=suggestion,
            category=self.category,
            source_line=ctx.line_text(lineno),
        )

    def meta(self, enabled: bool = True) -> RuleMeta:
        return RuleMeta(
            name=self.name,
            category=self.category,
            default_severity=self.default_severity,
            description=self.description,
            enabled=enabled,
        )


_REGISTRY: Dict[str, type] = {}


def register(name: str):
    """注册装饰器：将规则类登记到注册表。"""

    def deco(cls):
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return deco


def get_rule_class(name: str) -> type:
    if name not in _REGISTRY:
        raise KeyError(f"未知规则: {name}")
    return _REGISTRY[name]


def all_rule_metas(enabled_map: Optional[Dict[str, bool]] = None) -> List[RuleMeta]:
    """列出注册表中全部规则的元信息（--list-rules 使用）。"""
    metas = []
    for name, cls in sorted(_REGISTRY.items()):
        enabled = (enabled_map or {}).get(name, cls.enabled)
        metas.append(cls().meta(enabled=enabled))
    return metas
