"""报告格式化：JSON（机器可读）、Markdown（文档可贴）、HTML（可视化自查）。"""

from __future__ import annotations

import html
import json
from typing import Any, Dict, List

from .models import ERROR, FileReview, INFO, Issue, WARNING

_SEVERITY_BADGE = {ERROR: ("🔴", "error"), WARNING: ("🟠", "warning"), INFO: ("🔵", "info")}


def format_json(report: Dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------- Markdown


def _md_issue_row(i: Issue) -> str:
    return (
        f"| {i.line} | {i.column} | {i.rule} | {i.severity} | {_esc(i.message)} | "
        f"{_esc(i.suggestion)} |"
    )


def _esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def format_markdown(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines: List[str] = [
        "# 代码评审报告",
        "",
        f"- **工具**: {report['tool']} v{report['version']}",
        f"- **生成时间**: {report['generated_at']}",
        f"- **场景**: {', '.join(report['scenarios']) or 'general'}",
        f"- **评审文件数**: {s['files']}（发现问题 {s['files_with_issues']} 个）",
        f"- **问题合计**: {s['total']}（error {s['error']} / warning {s['warning']} / info {s['info']}）",
        "",
    ]
    for r in report["results"]:
        c = r["counts"]
        lines.append(f"## `{r['file']}`")
        lines.append("")
        if not r["parse_success"]:
            se = r.get("syntax_error") or {}
            lines.append(f"> ⚠️ 语法解析失败: {se.get('message', '')}（第 {se.get('line')} 行）")
            lines.append("")
        if not r["issues"]:
            lines.append("✅ 未发现问题（parse_success=%s）" % r["parse_success"])
            lines.append("")
            continue
        lines.append(
            f"发现问题 **{c['total']}** 个"
            f"（error {c['error']} / warning {c['warning']} / info {c['info']}）"
        )
        lines.append("")
        lines.append("| 行 | 列 | 规则 | 严重程度 | 问题描述 | 修复建议 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for i in r["issues"]:
            lines.append(_md_issue_row(Issue.from_dict(i)))
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------------ HTML


def _sev_badge(sev: str) -> str:
    icon, cls = _SEVERITY_BADGE.get(sev, ("⚪", "info"))
    return f'<span class="badge {cls}">{icon} {sev}</span>'


def format_html(report: Dict[str, Any]) -> str:
    s = report["summary"]
    parts: List[str] = []
    parts.append(
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>代码评审报告</title>
<style>
:root { color-scheme: light; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
       margin: 0; background: #f5f6f8; color: #1f2329; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 24px 20px 60px; }
h1 { font-size: 22px; margin: 8px 0 4px; }
.meta { color: #646a73; font-size: 13px; margin-bottom: 20px; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }
.card { background: #fff; border-radius: 10px; padding: 14px 18px; min-width: 120px;
        box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.card .num { font-size: 26px; font-weight: 700; }
.card .lbl { font-size: 12px; color: #646a73; }
.card.error .num { color: #e5484d; } .card.warning .num { color: #f76b15; }
.card.info .num { color: #2f6fed; } .card.total .num { color: #1f2329; }
.file { background: #fff; border-radius: 10px; margin-bottom: 18px; overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.file h2 { font-size: 15px; margin: 0; padding: 12px 16px; border-bottom: 1px solid #eee;
           font-family: ui-monospace, Menlo, Consolas, monospace; }
.file h2 .count { float: right; font-size: 12px; color: #646a73; font-family: inherit; }
.ok { padding: 14px 16px; color: #2e7d32; font-size: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #f0f0f0;
         vertical-align: top; }
th { background: #fafbfc; color: #646a73; font-weight: 600; }
td.code { font-family: ui-monospace, Menlo, Consolas, monospace; }
.badge { padding: 2px 8px; border-radius: 999px; font-size: 12px; color: #fff; white-space: nowrap; }
.badge.error { background: #e5484d; } .badge.warning { background: #f76b15; }
.badge.info { background: #2f6fed; }
.snippet { font-family: ui-monospace, Menlo, Consolas, monospace; background: #f6f8fa;
           padding: 2px 6px; border-radius: 4px; font-size: 12px; color: #57606a;
           display: block; max-width: 460px; overflow-x: auto; white-space: pre; }
</style>
</head>
<body><div class="wrap">"""
    )
    parts.append(f"<h1>代码评审报告</h1>")
    parts.append(
        f'<p class="meta">工具 {report["tool"]} v{report["version"]} · '
        f'生成时间 {report["generated_at"]} · 场景 {", ".join(report["scenarios"]) or "general"}</p>'
    )
    parts.append(
        f'<div class="cards">'
        f'<div class="card error"><div class="num">{s["error"]}</div><div class="lbl">error 错误</div></div>'
        f'<div class="card warning"><div class="num">{s["warning"]}</div><div class="lbl">warning 警告</div></div>'
        f'<div class="card info"><div class="num">{s["info"]}</div><div class="lbl">info 提示</div></div>'
        f'<div class="card total"><div class="num">{s["total"]}</div><div class="lbl">总计 / {s["files"]} 个文件</div></div>'
        f"</div>"
    )

    for r in report["results"]:
        c = r["counts"]
        parts.append(f'<div class="file"><h2>{html.escape(r["file"])}')
        parts.append(
            f'<span class="count">{c["total"]} 个问题（error {c["error"]} / '
            f'warning {c["warning"]} / info {c["info"]}）</span></h2>'
        )
        if not r["parse_success"]:
            se = r.get("syntax_error") or {}
            parts.append(
                f'<div class="ok">⚠️ 语法解析失败: {html.escape(str(se.get("message", "")))}'
                f'（第 {se.get("line")} 行）</div>'
            )
        if not r["issues"]:
            parts.append('<div class="ok">✅ 未发现问题</div>')
            parts.append("</div>")
            continue
        parts.append("<table><thead><tr><th>行</th><th>列</th><th>规则</th><th>严重程度</th><th>问题描述</th><th>修复建议</th></tr></thead><tbody>")
        for i in r["issues"]:
            i = Issue.from_dict(i)
            parts.append(
                f'<tr><td class="code">{i.line}</td><td class="code">{i.column}</td>'
                f'<td class="code">{html.escape(i.rule)}</td><td>{_sev_badge(i.severity)}</td>'
                f'<td>{html.escape(i.message)}'
                + (f'<span class="snippet">{html.escape(i.source_line)}</span>' if i.source_line else "")
                + "</td>"
                f'<td>{html.escape(i.suggestion)}</td></tr>'
            )
        parts.append("</tbody></table></div>")

    parts.append("</div></body></html>")
    return "".join(parts)


FORMATTERS = {
    "json": format_json,
    "markdown": format_markdown,
    "html": format_html,
}


def render(format_name: str, report: Dict[str, Any]) -> str:
    if format_name not in FORMATTERS:
        raise KeyError(f"未知输出格式: {format_name}")
    return FORMATTERS[format_name](report)
