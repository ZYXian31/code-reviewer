"""数据模型：问题(Issue)、规则(Rule)、文件评审结果(FileReview)、整体报告(Report)。"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 严重程度常量
ERROR = "error"
WARNING = "warning"
INFO = "info"

SEVERITIES = (ERROR, WARNING, INFO)
SEVERITY_RANK = {ERROR: 0, WARNING: 1, INFO: 2}
SEVERITY_CN = {ERROR: "错误", WARNING: "警告", INFO: "提示"}


@dataclass
class Issue:
    """一条评审发现的问题。

    Attributes:
        rule: 规则名称（与配置/标准答案中的规则名一致）。
        severity: 严重程度 error/warning/info。
        line: 1-based 行号。
        column: 1-based 列号。
        message: 问题描述（面向用户，输出信息示例与作业要求对齐）。
        suggestion: 修复建议。
        category: 规则类别（语法严重错误/规范/逻辑/性能/特定场景）。
        source_line: 问题所在行的源码片段（便于报告展示）。
    """

    rule: str
    severity: str
    line: int
    column: int
    message: str
    suggestion: str = ""
    category: str = ""
    source_line: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "suggestion": self.suggestion,
            "category": self.category,
            "source_line": self.source_line,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Issue":
        return cls(
            rule=d["rule"],
            severity=d["severity"],
            line=d["line"],
            column=d.get("column", 1),
            message=d.get("message", ""),
            suggestion=d.get("suggestion", ""),
            category=d.get("category", ""),
            source_line=d.get("source_line", ""),
        )


@dataclass
class RuleMeta:
    """规则的静态元信息（用于 --list-rules 与配置校验）。"""

    name: str
    category: str
    default_severity: str
    description: str
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class FileReview:
    """单个文件的评审结果。"""

    file: str
    language: str = "python"
    scenario: str = "general"
    parse_success: bool = True
    syntax_error: Optional[Dict[str, Any]] = None  # {"message":..., "line":...}
    issues: List[Issue] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        return {
            "error": sum(1 for i in self.issues if i.severity == ERROR),
            "warning": sum(1 for i in self.issues if i.severity == WARNING),
            "info": sum(1 for i in self.issues if i.severity == INFO),
            "total": len(self.issues),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "language": self.language,
            "scenario": self.scenario,
            "parse_success": self.parse_success,
            "syntax_error": self.syntax_error,
            "counts": self.counts(),
            "issues": [i.to_dict() for i in self.issues],
        }
