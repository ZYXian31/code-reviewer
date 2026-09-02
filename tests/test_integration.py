"""集成测试：在作业配套测试集（11 个用例 + 标准答案）上端到端验证。

红线断言：
1. 正例（test_case_01/02）必须零问题；
2. error 级问题（assign-in-condition / undefined-variable / unbalanced-bracket）零漏报；
3. 场景切换：test_case_10 通用场景零问题、批改场景检出 scenario-rule。
"""

import json
import os
import unittest

from code_reviewer.config import RulesConfig, ScenarioConfig
from code_reviewer.engine import ReviewEngine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTCASES = os.path.join(REPO, "code_review_testcases")
EXPECTED = os.path.join(TESTCASES, "expected_results.json")

TOLERANCE = 3  # 行号容差（标准答案行号与测试文件实际行号存在偏移）


def load_expected():
    with open(EXPECTED, "r", encoding="utf-8") as f:
        return json.load(f)["test_cases"]


class TestTestCaseSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rules_config = RulesConfig.load()
        general = ScenarioConfig.load("general")
        grading = ScenarioConfig.load("grading")
        engine = ReviewEngine(rules_config)
        cls.engine = engine
        cls.general = general
        cls.grading = grading

    def _review(self, name, scenario):
        path = os.path.join(TESTCASES, name)
        return self.engine.review_file(path, scenario_config=scenario)

    def test_positive_cases_clean(self):
        for name in ("test_case_01_correct.py", "test_case_02_correct.py"):
            r = self._review(name, self.general)
            self.assertEqual(r.issues, [], f"{name} 不应有问题: {[i.message for i in r.issues]}")

    def test_all_expected_rules_found(self):
        expected_cases = {c["file"]: c for c in load_expected()}
        for name, exp in expected_cases.items():
            if name == "test_case_10_scenario_rule.py":
                continue  # 场景用例单独验证
            r = self._review(name, self.general)
            found = {
                (i.rule, i.severity)
                for i in r.issues
            }
            for e in exp["expected_issues"]:
                self.assertIn(
                    (e["rule"], e["severity"]),
                    found,
                    f"{name}: 应检出 {e['rule']}({e['severity']})，实际 {sorted(found)}",
                )
                # 行号在容差范围内
                candidates = [i for i in r.issues if i.rule == e["rule"]]
                self.assertTrue(
                    any(abs(i.line - e["line"]) <= TOLERANCE for i in candidates),
                    f"{name}: {e['rule']} 行号偏差过大（期望近 {e['line']}，实际 "
                    f"{[i.line for i in candidates]}）",
                )

    def test_zero_error_miss(self):
        """红线：全部 error 级问题必须检出。"""
        expected_cases = {c["file"]: c for c in load_expected()}
        for name, exp in expected_cases.items():
            if name == "test_case_10_scenario_rule.py":
                continue
            r = self._review(name, self.general)
            got = {(i.rule) for i in r.issues if i.severity == "error"}
            for e in exp["expected_issues"]:
                if e["severity"] == "error":
                    self.assertIn(e["rule"], got, f"{name}: error 级 {e['rule']} 漏报！")

    def test_case_10_scenario_switch(self):
        general = self._review("test_case_10_scenario_rule.py", self.general)
        self.assertEqual(general.issues, [], "通用场景下 test_case_10 不应有问题")
        grading = self._review("test_case_10_scenario_rule.py", self.grading)
        scenario_issues = [i for i in grading.issues if i.rule == "scenario-rule"]
        self.assertEqual(len(scenario_issues), 1, "批改场景应检出 1 条 scenario-rule")
        self.assertEqual(scenario_issues[0].severity, "warning")

    def test_case_11_three_orjson_warnings(self):
        r = self._review("test_case_11_prefer_orjson.py", self.general)
        oj = [i for i in r.issues if i.rule == "prefer-orjson"]
        self.assertEqual(len(oj), 3)

    def test_case_09_expected_three_plus_math(self):
        r = self._review("test_case_09_multiple_issues.py", self.general)
        rules = sorted(i.rule for i in r.issues)
        # 标准答案列出 3 条；工具额外检出 `import math` 确实未使用（标准答案遗漏）
        self.assertEqual(rules, ["undefined-variable", "unused-import", "unused-import", "unused-variable"])


if __name__ == "__main__":
    unittest.main()
