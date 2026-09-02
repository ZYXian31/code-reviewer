"""单元测试：unused-import / bare-except / prefer-orjson / scenario-rule / 引擎配置。"""

import unittest

from code_reviewer.engine import ReviewEngine
from code_reviewer.config import RulesConfig, ScenarioConfig


def review(src, scenario=None):
    sc = ScenarioConfig.load(scenario) if scenario else None
    return ReviewEngine(RulesConfig.load()).review_source(src, filename="<test>", scenario_config=sc)


class TestUnusedImport(unittest.TestCase):
    def test_unused_module(self):
        src = "import os\nimport sys\n"
        r = review(src)
        msgs = [i.message for i in r.issues if i.rule == "unused-import"]
        self.assertEqual(msgs, ["导入的 `os` 未被使用", "导入的 `sys` 未被使用"])
        self.assertEqual(r.issues[0].severity, "info")

    def test_used_via_attribute(self):
        src = "import os\nprint(os.path.join('a'))\n"
        r = review(src)
        self.assertNotIn("unused-import", [i.rule for i in r.issues])

    def test_annotation_counts_as_use(self):
        src = "from typing import List\n\ndef f(x: List[int]) -> None:\n    pass\n"
        r = review(src)
        self.assertNotIn("unused-import", [i.rule for i in r.issues])

    def test_from_import(self):
        src = "from collections import deque\nfrom textwrap import dedent\n"
        r = review(src)
        msgs = [i.message for i in r.issues if i.rule == "unused-import"]
        self.assertEqual(msgs, ["导入的 `deque` 未被使用", "导入的 `dedent` 未被使用"])

    def test_alias(self):
        src = "import numpy as np\n"
        r = review(src)
        msgs = [i.message for i in r.issues if i.rule == "unused-import"]
        self.assertEqual(msgs, ["导入的 `np` 未被使用"])

    def test_try_import_not_flagged(self):
        src = "try:\n    import ujson as json\nexcept ImportError:\n    import json\n"
        r = review(src)
        self.assertNotIn("unused-import", [i.rule for i in r.issues])


class TestBareExcept(unittest.TestCase):
    def test_bare(self):
        src = "def f():\n    try:\n        return 1\n    except:\n        return 0\n"
        r = review(src)
        msg = [i.message for i in r.issues if i.rule == "bare-except"]
        self.assertEqual(msg, ["建议指定捕获的异常类型"])
        self.assertEqual(r.issues[0].severity, "warning")

    def test_typed_not_flagged(self):
        src = "def f():\n    try:\n        return 1\n    except ValueError as e:\n        return 0\n    except Exception:\n        return -1\n"
        r = review(src)
        self.assertNotIn("bare-except", [i.rule for i in r.issues])


class TestPreferOrjson(unittest.TestCase):
    def test_import_and_calls(self):
        src = "import json\n\ndef f(s):\n    return json.loads(s)\n\ndef g(d):\n    return json.dumps(d)\n"
        r = review(src)
        msgs = [i.message for i in r.issues if i.rule == "prefer-orjson"]
        self.assertEqual(len(msgs), 3)
        self.assertIn("建议使用 orjson.loads 替代 json.loads", msgs)

    def test_orjson_not_flagged(self):
        src = "import orjson\nprint(orjson.loads('{}'))\n"
        r = review(src)
        self.assertNotIn("prefer-orjson", [i.rule for i in r.issues])


class TestScenarioRule(unittest.TestCase):
    GRADING_SRC = (
        'def calculate_result(answer, reference):\n'
        '    """计算批改结果"""\n'
        '    return 100 if answer == reference else 0\n'
        '\n'
        'def grade_submission(student_id, score):\n'
        '    return {"student_id": student_id, "score": score}\n'
    )

    def test_general_no_scenario_rule(self):
        r = review(self.GRADING_SRC)
        self.assertEqual([i.rule for i in r.issues], [])

    def test_grading_flags_violation(self):
        r = review(self.GRADING_SRC, scenario="grading")
        issues = [i for i in r.issues if i.rule == "scenario-rule"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 1)
        self.assertEqual(issues[0].severity, "warning")

    def test_grading_compliant_function_ok(self):
        r = review('def score_answer(a, b):\n    return a == b\n', scenario="grading")
        self.assertNotIn("scenario-rule", [i.rule for i in r.issues])


class TestEngineConfig(unittest.TestCase):
    def test_disable_rule(self):
        cfg = RulesConfig({"rules": {"unused-variable": {"enabled": False}}})
        engine = ReviewEngine(cfg)
        r = engine.review_source("def f():\n    a = 1\n    return 2\n", filename="<test>")
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])

    def test_severity_override(self):
        cfg = RulesConfig({"rules": {"unused-variable": {"enabled": True, "severity": "error"}}})
        engine = ReviewEngine(cfg)
        r = engine.review_source("def f():\n    a = 1\n    return 2\n", filename="<test>")
        self.assertEqual(r.issues[0].severity, "error")

    def test_issue_has_suggestion_and_snippet(self):
        r = review("def f():\n    a = 1\n    return 2\n")
        i = r.issues[0]
        self.assertTrue(i.suggestion)
        self.assertTrue(i.source_line)

    def test_bad_file_isolated(self):
        engine = ReviewEngine(RulesConfig.load())
        r = engine.review_file("/不存在/的文件.py")
        self.assertEqual(r.issues[0].rule, "internal-error")


if __name__ == "__main__":
    unittest.main()
