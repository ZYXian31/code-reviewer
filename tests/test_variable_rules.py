"""单元测试：变量规则（unused-variable / undefined-variable）。"""

import unittest

from code_reviewer.engine import ReviewEngine
from code_reviewer.config import RulesConfig


def review(src):
    return ReviewEngine(RulesConfig.load()).review_source(src, filename="<test>")


class TestUnusedVariable(unittest.TestCase):
    def test_basic_unused(self):
        src = "def f():\n    a = 1\n    b = 2\n    return b\n"
        r = review(src)
        unused = [i.message for i in r.issues if i.rule == "unused-variable"]
        self.assertEqual(unused, ["变量 `a` 声明后未被使用"])
        self.assertEqual(r.issues[0].severity, "warning")

    def test_module_level_not_flagged(self):
        src = "public_config = 1\nPUBLIC = 'x'\n"
        r = review(src)
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])

    def test_underscore_not_flagged(self):
        src = "def f():\n    _tmp = 1\n    _ = 2\n    return 0\n"
        r = review(src)
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])

    def test_params_not_flagged(self):
        src = "def f(a, b):\n    return 1\n"
        r = review(src)
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])

    def test_unpacking(self):
        src = "def f():\n    a, b = 1, 2\n    return a\n"
        r = review(src)
        unused = [i.message for i in r.issues if i.rule == "unused-variable"]
        self.assertEqual(unused, ["变量 `b` 声明后未被使用"])

    def test_for_target_used(self):
        src = "def f(nums):\n    total = 0\n    for n in nums:\n        total += n\n    return total\n"
        r = review(src)
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])

    def test_for_target_unused(self):
        src = "def f():\n    for i in range(3):\n        pass\n"
        r = review(src)
        self.assertIn("unused-variable", [i.rule for i in r.issues])

    def test_except_as_not_flagged(self):
        src = "def f():\n    try:\n        return 1\n    except ValueError as e:\n        return 0\n"
        r = review(src)
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])

    def test_nested_use_of_outer(self):
        src = "def outer():\n    x = 1\n    def inner():\n        return x\n    return inner()\n"
        r = review(src)
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])

    def test_class_scope_not_flagged(self):
        src = "class A:\n    value = 1\n"
        r = review(src)
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])

    def test_augassign_counts_as_use(self):
        src = "def f():\n    x = 0\n    x += 1\n    return 1\n"
        r = review(src)
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])

    def test_bare_annotation_not_flagged(self):
        src = "def f():\n    x: int\n    return 1\n"
        r = review(src)
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])

    def test_walrus(self):
        src = "def f():\n    if (y := len([1])) > 0:\n        return y\n"
        r = review(src)
        self.assertNotIn("unused-variable", [i.rule for i in r.issues])


class TestUndefinedVariable(unittest.TestCase):
    def test_basic(self):
        src = "def f():\n    return x + 1\n"
        r = review(src)
        undefined = [i.message for i in r.issues if i.rule == "undefined-variable"]
        self.assertEqual(undefined, ["引用了未定义的变量 `x`"])
        self.assertEqual(r.issues[0].severity, "error")

    def test_builtins_not_flagged(self):
        src = "def f(x):\n    print(len(x), sum(x), round(1.2), str(x), ValueError('x'))\n"
        r = review(src)
        self.assertEqual(r.issues, [])

    def test_dunder_not_flagged(self):
        src = "if __name__ == '__main__':\n    print('ok')\n"
        r = review(src)
        self.assertEqual(r.issues, [])

    def test_module_level_forward_ref(self):
        src = "def f():\n    return helper()\n\ndef helper():\n    return 1\n"
        r = review(src)
        self.assertNotIn("undefined-variable", [i.rule for i in r.issues])

    def test_class_attr_not_visible_in_method(self):
        # 与方法内裸引用类属性在运行时会 NameError（pyflakes 同样报告）
        src = "class A:\n    v = 1\n    def m(self):\n        return v\n"
        r = review(src)
        self.assertIn("undefined-variable", [i.rule for i in r.issues])

    def test_global_usage(self):
        src = "LIMIT = 10\n\ndef f():\n    return LIMIT\n"
        r = review(src)
        self.assertNotIn("undefined-variable", [i.rule for i in r.issues])

    def test_import_binding(self):
        src = "import os\n\ndef f():\n    return os.path.join('a')\n"
        r = review(src)
        self.assertNotIn("undefined-variable", [i.rule for i in r.issues])


if __name__ == "__main__":
    unittest.main()
