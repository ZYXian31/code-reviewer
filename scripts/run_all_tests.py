#!/usr/bin/env python3
"""批量评审测试代码集。

用法（在项目根目录）:
    python scripts/run_all_tests.py                        # 通用场景评审全部用例
    python scripts/run_all_tests.py --scenario grading     # 批改场景评审全部用例
    python scripts/run_all_tests.py --compare              # 评审后自动与标准答案对比

输出:
    reports/testset_general/      每个文件 JSON + 合并的 summary.{json,markdown,html}
    reports/compare_report.json   与 expected_results.json 的对比结果
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from code_reviewer.config import RulesConfig, ScenarioConfig  # noqa: E402
from code_reviewer.engine import ReviewEngine, build_report  # noqa: E402

DEFAULT_TESTCASES = os.path.join(REPO, "code_review_testcases") if os.path.isdir(
    os.path.join(REPO, "code_review_testcases")
) else "/tmp/task/code_review_testcases"


def run_all(test_dir: str, scenario: str, output_dir: str, per_file: bool = True) -> list:
    engine = ReviewEngine(RulesConfig.load())
    scenario_config = ScenarioConfig.load(scenario)
    files = sorted(f for f in os.listdir(test_dir) if f.endswith(".py"))
    reviews = []
    for name in files:
        reviews.append(engine.review_file(os.path.join(test_dir, name), scenario_config=scenario_config))

    report = build_report([r for r in reviews])
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    if per_file:
        for r in reviews:
            name = os.path.splitext(os.path.basename(r.file))[0]
            with open(os.path.join(output_dir, f"{name}_review.json"), "w", encoding="utf-8") as f:
                json.dump(r.to_dict(), f, ensure_ascii=False, indent=2)
    return reviews


def load_expected(expected_path: str):
    with open(expected_path, "r", encoding="utf-8") as f:
        return json.load(f)["test_cases"]


def compare(reviews: list, expected_path: str, line_tolerance: int = 3,
            override: dict | None = None) -> dict:
    """与标准答案对比：按 (规则名, 行号容差) 匹配，统计漏报/误报。

    override: {文件名: FileReview}，用于场景用例（如 test_case_10 在批改场景下评审）。
    """
    cases = load_expected(expected_path)
    expected_cases = {c["file"]: c for c in cases}
    reviews = {os.path.basename(r.file): r for r in reviews}
    if override:
        reviews.update({k: v for k, v in override.items()})
    result = {"line_tolerance": line_tolerance, "cases": [], "summary": {}}
    total_missed = total_extra = total_error_missed = 0

    for review in reviews.values():
        base = os.path.basename(review.file)
        exp = expected_cases.get(base)
        missed = []
        if exp is None:
            extra = list(review.issues)
            matched_exp = []
        else:
            matched_exp = []
            extra = []
            used_tool = set()
            for e in exp["expected_issues"]:
                candidates = [
                    (idx, i)
                    for idx, i in enumerate(review.issues)
                    if i.rule == e["rule"] and abs(i.line - e["line"]) <= line_tolerance
                    and idx not in used_tool
                ]
                if candidates:
                    idx, best = candidates[0]
                    used_tool.add(idx)
                    matched_exp.append((e, best))
                else:
                    missed.append(e)
            extra = [i for idx, i in enumerate(review.issues) if idx not in used_tool]

        missed_err = [m for m in missed if m["severity"] == "error"]
        extra_err = [i for i in extra if i.severity == "error"]
        total_missed += len(missed)
        total_extra += len(extra)
        total_error_missed += len(missed_err)
        case = {
            "file": base,
            "expected_count": len(exp["expected_issues"]) if exp else 0,
            "actual_count": len(review.issues),
            "matched": len(matched_exp),
            "missed": [
                {"line": m["line"], "rule": m["rule"], "severity": m["severity"], "message": m["message"]}
                for m in missed
            ],
            "extra": [
                {"line": i.line, "rule": i.rule, "severity": i.severity, "message": i.message}
                for i in extra
            ],
            "line_deltas": [abs(e["line"] - best.line) for (e, best) in matched_exp],
        }
        result["cases"].append(case)

    result["summary"] = {
        "total_expected": sum(len(c["expected_issues"]) for c in cases),
        "total_missed": total_missed,
        "total_extra": total_extra,
        "error_missed": total_error_missed,
        "error_extra": sum(1 for c in result["cases"] for i in c["extra"] if i["severity"] == "error"),
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--test-dir", default=DEFAULT_TESTCASES)
    ap.add_argument("--scenario", default="general")
    ap.add_argument("--output-dir", default=os.path.join(REPO, "reports", "testset_general"))
    ap.add_argument("--expected", default=os.path.join(DEFAULT_TESTCASES, "expected_results.json"))
    ap.add_argument("--compare", action="store_true")
    args = ap.parse_args()

    reviews = run_all(args.test_dir, args.scenario, args.output_dir)
    for r in reviews:
        c = r.counts()
        print(f"{os.path.basename(r.file):<40} parse_ok={r.parse_success!s:<5} "
              f"issues={c['total']} (error {c['error']} / warning {c['warning']} / info {c['info']})")

    if args.compare:
        # 场景切换验证：test_case_10 额外以"批改场景"评审
        grading_out = os.path.join(REPO, "reports", "testset_grading")
        grading_reviews = run_all(args.test_dir, "grading", grading_out)
        override = {}
        for r in grading_reviews:
            if os.path.basename(r.file) == "test_case_10_scenario_rule.py":
                override["test_case_10_scenario_rule.py"] = r
        cmp = compare(reviews, args.expected, override=override)
        out = os.path.join(REPO, "reports", "compare_report.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(cmp, f, ensure_ascii=False, indent=2)
        s = cmp["summary"]
        print(
            f"\n对比结果: 漏报 {s['total_missed']} / 多报 {s['total_extra']} / "
            f"error级漏报 {s['error_missed']}（红线）"
        )
        for case in cmp["cases"]:
            flag = "✅" if not case["missed"] and not case["extra"] else (
                "⚠️ error漏报!" if any(m["severity"] == "error" for m in case["missed"])
                else "❌ 有差异" if case["missed"] or case["extra"] else "✅"
            )
            print(f"  {flag} {case['file']}: expected {case['expected_count']}, "
                  f"actual {case['actual_count']}, missed {len(case['missed'])}, extra {len(case['extra'])}")
        return 1 if s["error_missed"] > 0 else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
