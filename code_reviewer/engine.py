"""评审引擎：代码导入 → 语法解析(AST) → 规则检查 → 问题定位与分级 → 结构化报告。

流程说明：
1. 读取源码（UTF-8，异常字符替换，绝不因编码问题中止评审）；
2. ast.parse 解析；成功 → 执行全部启用规则（含场景规则）；
   失败 → 走"恢复路径"：assign-in-condition / unbalanced-bracket 可识别的具体缺陷
   优先定位；两者都不命中时才报通用 syntax-error（避免同一文件重复报错）；
3. 问题统一去重 + 按 (行, 列, 严重程度) 排序；
4. 汇总为 FileReview，可输出 JSON/Markdown/HTML。
"""

from __future__ import annotations

import ast
import traceback
from typing import Any, Dict, List, Optional

from . import __version__
from .config import RulesConfig, ScenarioConfig
from .logger import get_logger
from .models import ERROR, FileReview, Issue, SEVERITY_RANK
from .rules import scenario_rules as scenario_module
from .rules.base import RuleContext, get_rule_class

log = get_logger()

_CORE_RULES = [
    "assign-in-condition",
    "syntax-error",
    "unbalanced-bracket",
    "unused-variable",
    "undefined-variable",
    "unused-import",
    "bare-except",
    "prefer-orjson",
]


def read_source(path: str) -> str:
    """读取源码：UTF-8 优先，异常字符替换处理；完全无法解码时回退 GBK/errors=replace。"""
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            with open(path, "r", encoding=enc, errors="replace" if enc != "utf-8" else "strict") as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


class ReviewEngine:
    """评审引擎：按配置运行规则集。"""

    def __init__(self, rules_config: Optional[RulesConfig] = None):
        self.rules_config = rules_config or RulesConfig.load()

    def review_source(
        self,
        source: str,
        filename: str = "<string>",
        scenario_config: Optional[ScenarioConfig] = None,
    ) -> FileReview:
        """评审一段源码。"""
        scenario = scenario_config.name if scenario_config else "general"
        review = FileReview(file=filename, scenario=scenario)
        lines = source.splitlines()
        tree: Optional[ast.Module] = None
        parse_error: Optional[Exception] = None
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError as e:
            parse_error = e
            review.parse_success = False
            review.syntax_error = {
                "message": getattr(e, "msg", str(e)),
                "line": getattr(e, "lineno", None),
                "column": getattr(e, "offset", None),
            }
            log.debug("语法解析失败 %s: %s", filename, e)
        except Exception as e:  # noqa: BLE001 - 解析阶段任何异常都应被捕获
            parse_error = e
            review.parse_success = False
            log.warning("解析 %s 时出现异常: %s", filename, e)

        ctx = RuleContext(
            source=source,
            lines=lines,
            tree=tree,
            parse_error=parse_error,
            scenario=scenario,
        )

        # 恢复路径 + 通用规则
        rules_to_run = self._plan_rules(review.parse_success, scenario_config)
        issues: List[Issue] = []
        for rule in rules_to_run:
            try:
                new_issues = rule.check(ctx)
                if new_issues:
                    issues.extend(new_issues)
            except Exception as e:  # noqa: BLE001 - 单条规则异常不影响整体
                log.warning("规则 %s 执行失败（%s）: %s", rule.name, filename, e)
                log.debug(traceback.format_exc())

        # 恢复路径已精确定位具体缺陷（assign-in-condition / unbalanced-bracket）时，
        # 不再重复报告通用 syntax-error（避免同一文件双报，影响漏报/误报统计）
        if not review.parse_success and issues:
            specific = {i.rule for i in issues} & {"assign-in-condition", "unbalanced-bracket"}
            if specific:
                issues = [i for i in issues if i.rule != "syntax-error"]

        review.issues = self._dedupe_and_sort(issues)
        return review

    # ------------------------------------------------------------------ 内部
    def _plan_rules(
        self,
        parse_success: bool,
        scenario_config: Optional[ScenarioConfig],
    ) -> List[Any]:
        """决定本文件执行哪些规则实例。"""
        enabled_core = [n for n in _CORE_RULES if self.rules_config.is_enabled(n)]
        instances: List[Any] = []

        # AST 规则（仅解析成功时可运行）；语法恢复规则（仅解析失败时运行）
        for name in enabled_core:
            cls = get_rule_class(name)
            inst = cls()
            sev = self.rules_config.severity_for(name, cls.default_severity)
            if sev != cls.default_severity:
                inst.default_severity = sev
            instances.append(inst)

        if parse_success:
            # 场景规则：通用规则之上叠加场景专属规则（配置驱动）
            if scenario_config is not None and self.rules_config.is_enabled("scenario-rule"):
                instances.extend(scenario_module.build_scenario_rules(scenario_config))
        else:
            # AST 失败恢复：只保留能脱离 AST 工作的规则
            instances = [
                inst
                for inst in instances
                if inst.name in ("assign-in-condition", "unbalanced-bracket", "syntax-error")
            ]

        # 场景检查顺序：syntax-error 永远作为最后兜底
        instances.sort(key=lambda r: 1 if r.name == "syntax-error" else 0)
        return instances

    def review_file(
        self,
        path: str,
        scenario_config: Optional[ScenarioConfig] = None,
    ) -> FileReview:
        """评审一个文件（带日志与异常隔离，单个文件失败不中断批处理）。"""
        display = path
        try:
            source = read_source(path)
            review = self.review_source(source, filename=display, scenario_config=scenario_config)
            log.info("评审完成 %s: %d 个问题", display, len(review.issues))
            return review
        except Exception as e:  # noqa: BLE001
            log.error("评审 %s 失败: %s", display, e)
            log.debug(traceback.format_exc())
            review = FileReview(file=display, scenario=scenario_config.name if scenario_config else "general")
            review.parse_success = False
            review.issues = [
                Issue(
                    rule="internal-error",
                    severity=ERROR,
                    line=1,
                    column=1,
                    message=f"工具内部错误，未能评审该文件：{e}",
                    suggestion="请检查文件是否为合法的文本源码",
                    category="工具",
                )
            ]
            return review

    # ------------------------------------------------------------------ 输出整理
    @staticmethod
    def _dedupe_and_sort(issues: List[Issue]) -> List[Issue]:
        seen = set()
        uniq: List[Issue] = []
        for i in issues:
            key = (i.rule, i.line, i.column, i.message)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(i)
        uniq.sort(key=lambda i: (i.line if i.line else 999999, i.column, SEVERITY_RANK.get(i.severity, 9), i.rule))
        return uniq


def summarize(reviews: List[FileReview]) -> Dict[str, Any]:
    """汇总多文件结果：按严重程度计数。"""
    summary: Dict[str, Any] = {
        "files": len(reviews),
        "files_with_issues": sum(1 for r in reviews if r.issues),
        "error": 0,
        "warning": 0,
        "info": 0,
        "total": 0,
    }
    for r in reviews:
        c = r.counts()
        summary["error"] += c["error"]
        summary["warning"] += c["warning"]
        summary["info"] += c["info"]
        summary["total"] += c["total"]
    return summary


def build_report(reviews: List[FileReview]) -> Dict[str, Any]:
    """构建完整报告字典（JSON 序列化友好）。"""
    return {
        "tool": "code-reviewer",
        "version": __version__,
        "generated_at": _now_iso(),
        "scenarios": sorted({r.scenario for r in reviews}),
        "summary": summarize(reviews),
        "results": [r.to_dict() for r in reviews],
    }


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")
