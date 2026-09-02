"""命令行入口：code_reviewer / python -m code_reviewer。

示例:
    # 评审单个文件（输出 JSON/Markdown/HTML 三份报告到 reports/）
    python -m code_reviewer tests/data/test_case_03_assign_in_condition.py

    # 批量评审目录
    python -m code_reviewer --output-dir reports/testset code_review_testcases/

    # 场景切换评审（批改场景）
    python -m code_reviewer --scenario grading test_case_10_scenario_rule.py

    # 从标准输入评审一段代码
    echo 'if x = 1:' | python -m code_reviewer --stdin

    # 查看规则清单
    python -m code_reviewer --list-rules
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import webbrowser
from typing import List, Optional

from . import __version__, formatters
from .config import DEFAULT_RULES_CONFIG, ConfigError, RulesConfig, ScenarioConfig
from .engine import ReviewEngine, build_report, summarize
from .logger import get_logger, setup_logging
from .models import SEVERITIES
from .rules.base import all_rule_metas
from .uploader import UploadError, upload_markdown

log = get_logger()

_COLOR = {"red": "\033[31m", "yellow": "\033[33m", "blue": "\033[34m", "reset": "\033[0m"}


def _severity_color(sev: str) -> str:
    return {"error": "red", "warning": "yellow", "info": "blue"}.get(sev, "reset")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="code_reviewer",
        description="面向特定场景的代码评审工具（AST 静态分析）",
        epilog="完整工作链路：代码导入 → 语法解析(AST) → 规则检查 → 问题定位与分级 → 结构化报告输出。",
    )
    p.add_argument("paths", nargs="*", help="待评审的 Python 文件或目录（目录会递归遍历 *.py）")
    p.add_argument("-s", "--scenario", default="general",
                   help="业务场景（内置: general/grading；也可传自定义场景 JSON 路径），默认 general")
    p.add_argument("-c", "--rules-config", default=DEFAULT_RULES_CONFIG,
                   help="规则配置文件路径（控制规则启停与严重程度），默认 config/rules.json")
    p.add_argument("-o", "--output-dir", default="reports", help="报告输出目录，默认 ./reports")
    p.add_argument("-f", "--format", choices=["json", "markdown", "html", "all"], default="all",
                   help="报告格式，默认 all（同时输出三种）")
    p.add_argument("--per-file", action="store_true",
                   help="为每个文件额外输出独立的 JSON 评审结果")
    p.add_argument("--stdin", action="store_true", help="从标准输入读取代码（文件名显示为 <stdin>）")
    p.add_argument("--list-rules", action="store_true", help="列出当前启用的全部规则并退出")
    p.add_argument("--upload", action="store_true", help="评审后尝试将 Markdown 报告上传到 i 讯飞云文档")
    p.add_argument("--upload-title", default="代码评审报告", help="上传云文档时的标题")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.add_argument("--log-file", default="", help="日志文件路径（默认仅控制台）")
    p.add_argument("--no-color", action="store_true", help="关闭控制台彩色输出")
    p.add_argument("--no-open", action="store_true", help="不自动打开 HTML 报告")
    p.add_argument("--strict", action="store_true", help="发现 error 级问题时以非零退出码结束")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _collect_py_files(paths: List[str]) -> List[str]:
    files: List[str] = []
    for p in paths:
        if os.path.isfile(p):
            files.append(p)
        elif os.path.isdir(p):
            for root, _, names in os.walk(p):
                for n in sorted(names):
                    if n.endswith(".py"):
                        files.append(os.path.join(root, n))
        else:
            log.warning("路径不存在，已跳过: %s", p)
    return files


def _print_console_report(review, use_color: bool) -> None:
    c = review.counts()
    marker = "✅" if c["total"] == 0 else "⚠️"
    line = f"  {marker} {review.file}: {c['total']} 个问题"
    if c["total"]:
        line += f"（error {c['error']} / warning {c['warning']} / info {c['info']}）"
    print(line)
    for i in review.issues:
        color = _severity_color(i.severity) if use_color else "reset"
        prefix = f"{_COLOR[color]}[{i.severity.upper()}]{_COLOR['reset']}" if use_color else f"[{i.severity.upper()}]"
        print(
            f"    {prefix} 第{i.line}行 第{i.column}列  {i.rule}: {i.message}"
            + (f"  →  {i.suggestion}" if i.suggestion else "")
        )


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(
        level=getattr(logging, args.log_level),
        log_file=args.log_file,
        console=args.log_level == "DEBUG" or True,
    )

    use_color = not args.no_color and sys.stdout.isatty()

    try:
        rules_config = RulesConfig.load(args.rules_config)
    except ConfigError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    if args.list_rules:
        metas = all_rule_metas()
        enabled = {m.name: rules_config.is_enabled(m.name) for m in metas}
        print(f"{'规则名称':<24}{'类别':<14}{'严重程度':<12}{'状态':<8}说明")
        for m in metas:
            sev = rules_config.severity_for(m.name, m.default_severity)
            print(f"{m.name:<24}{m.category:<14}{sev:<12}{'启用' if enabled[m.name] else '关闭':<8}{m.description}")
        print(f"\n共 {len(metas)} 条规则；规则启停与分级可在 {args.rules_config} 中配置。")
        return 0

    # 场景加载
    try:
        scenario_config = ScenarioConfig.load(args.scenario)
    except ConfigError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    engine = ReviewEngine(rules_config)
    reviews = []

    if args.stdin:
        source = sys.stdin.read()
        reviews.append(engine.review_source(source, filename="<stdin>", scenario_config=scenario_config))
    else:
        files = _collect_py_files(args.paths)
        if not files:
            print("错误: 未提供可评审的 Python 文件/目录（可用 --help 查看用法）", file=sys.stderr)
            return 2
        for f in files:
            reviews.append(engine.review_file(f, scenario_config=scenario_config))

    report = build_report(reviews)
    summary = report["summary"]
    print(f"\n评审完成: {summary['files']} 个文件，共 {summary['total']} 个问题"
          f"（error {summary['error']} / warning {summary['warning']} / info {summary['info']}）")

    for r in reviews:
        _print_console_report(r, use_color)

    # 保存报告
    os.makedirs(args.output_dir, exist_ok=True)
    formats = ["json", "markdown", "html"] if args.format == "all" else [args.format]
    saved: List[str] = []
    for fmt in formats:
        text = formatters.render(fmt, report)
        path = os.path.join(args.output_dir, f"review_summary.{fmt}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        saved.append(path)
        log.info("已保存报告: %s", path)

    if args.per_file:
        for r in reviews:
            name = os.path.splitext(os.path.basename(r.file))[0] or "stdin"
            path = os.path.join(args.output_dir, f"{name}_review.json")
            with open(path, "w", encoding="utf-8") as f:
                json_dump(r.to_dict(), f)
            saved.append(path)

    # 上传云文档（可选）
    if args.upload:
        md_text = formatters.render("markdown", report)
        try:
            result = upload_markdown(md_text, args.upload_title)
            print(f"已上传 i 讯飞云文档: {result}")
        except UploadError as e:
            print(f"上传失败（不影响本地报告）: {e}")

    if not args.no_open and "html" in saved:
        try:
            webbrowser.open("file://" + os.path.abspath(os.path.join(args.output_dir, "review_summary.html")))
        except Exception:  # noqa: BLE001
            pass

    if args.strict and summary["error"] > 0:
        return 1
    return 0


def json_dump(obj, fp) -> None:
    import json

    json.dump(obj, fp, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
