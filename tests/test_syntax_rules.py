"""单元测试：语法严重错误规则与 AST 恢复路径。"""

import ast
import unittest

from code_reviewer.engine import ReviewEngine
from code_reviewer.config import RulesConfig


def review(src, scenario=None):
    engine = ReviewEngine(RulesConfig.load())
    sc = None
    if scenario:
        from code_reviewer.config import ScenarioConfig

        sc = ScenarioConfig.load(scenario)
    return engine.review_source(src, filename="<test>", scenario_config=sc)


class TestAssignInCondition(unittest.TestCase):
    def test_basic(self):
        src = "if user_id = 100:\n    print(1)\n"
        r = review(src)
        self.assertFalse(r.parse_success)
        issues = [(i.rule, i.line, i.severity) for i in r.issues]
        self.assertIn(("assign-in-condition", 1, "error"), issues)
        # 不应重复报通用 syntax-error
        self.assertNotIn("syntax-error", [i.rule for i in r.issues])

    def test_elif_and_while(self):
        src = "if a == 1:\n    pass\nelif b = 2:\n    pass\nwhile c = 3:\n    pass\n"
        r = review(src)
        rules = [i.rule for i in r.issues]
        self.assertEqual(rules.count("assign-in-condition"), 2)

    def test_walrus_not_flagged(self):
        # 海象运算符合法，不应误报
        src = "if (x := compute()) > 0:\n    print(x)\n"
        r = review(src)
        self.assertTrue(r.parse_success)
        self.assertNotIn("assign-in-condition", [i.rule for i in r.issues])

    def test_comparison_not_flagged(self):
        src = "if a == b and c <= d and e != f:\n    pass\n"
        r = review(src)
        self.assertTrue(r.parse_success)
        self.assertNotIn("assign-in-condition", [i.rule for i in r.issues])

    def test_keyword_arg_not_flagged(self):
        src = "def f():\n    if check(x=1):\n        return\n"
        r = review(src)
        self.assertNotIn("assign-in-condition", [i.rule for i in r.issues])


class TestUnbalancedBracket(unittest.TestCase):
    def test_fstring_missing_brace(self):
        src = 'message = f"用户 {name} 年龄 {age"\n'
        r = review(src)
        self.assertFalse(r.parse_success)
        issues = [(i.rule, i.line, i.message) for i in r.issues]
        self.assertIn(("unbalanced-bracket", 1, "括号不匹配，缺少闭合的 `}`"), issues)
        self.assertNotIn("syntax-error", [i.rule for i in r.issues])

    def test_normal_parenthesis_unclosed(self):
        src = "x = (1 + 2\n"
        r = review(src)
        rules = [i.rule for i in r.issues]
        self.assertIn("unbalanced-bracket", rules)

    def test_fstring_balanced_ok(self):
        src = 'name = "a"\nprint(f"{name} ok")\n'
        r = review(src)
        self.assertTrue(r.parse_success)
        self.assertEqual(r.issues, [])

    def test_string_content_numbers_ignored(self):
        # 字符串里的括号不算代码括号
        src = 's = "(hello [world}"\n'
        r = review(src)
        self.assertTrue(r.parse_success)


class TestSyntaxErrorFallback(unittest.TestCase):
    def test_true_syntax_error(self):
        src = "x y = 1\n"
        r = review(src)
        self.assertFalse(r.parse_success)
        self.assertIn("syntax-error", [i.rule for i in r.issues])

    def test_bracket_error_classified_specifically(self):
        # `def f(:` 本质是缺 `)` → 由 unbalanced-bracket 精确定位（比通用 syntax-error 更有价值）
        src = "def f(:\n    pass\n"
        r = review(src)
        self.assertIn("unbalanced-bracket", [i.rule for i in r.issues])

    def test_error_is_red_line(self):
        src = "x = = 1\n"
        r = review(src)
        self.assertFalse(r.parse_success)
        self.assertTrue(r.issues)


if __name__ == "__main__":
    unittest.main()
