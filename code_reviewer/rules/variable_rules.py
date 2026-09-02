"""变量类规则：unused-variable（声明未使用）与 undefined-variable（引用未定义）。

实现方式：基于 AST 的完整作用域分析（模块/函数/类/lambda/推导式五类作用域），
收集绑定(binding)与使用(use)，再做一次解析(手写名字解析：当前作用域→外层→模块→builtins)。
参考 pyflakes 语义以控制误报：
- 模块作用域变量视为公开 API，不报 unused-variable；
- 函数参数、with-as、except-as、导入名不报 unused（导入由 unused-import 规则负责）；
- 下划线开头变量（约定忽略）不报；
- 类作用域不参与方法体的名字解析（与 Python 运行时一致）。
"""

from __future__ import annotations

import ast
import builtins as _builtins
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .base import BaseRule, RuleContext, register
from ..models import Issue

_UNUSED_SUGGESTION = "若该变量确实不需要，请删除；若为 API 预留，请在调用处使用或添加下划线前缀约定"
_UNDEFINED_SUGGESTION = "在使用前定义该变量，或检查变量名是否拼写错误"

_DUNDER_NAMES = {
    "__name__", "__file__", "__doc__", "__package__", "__loader__", "__spec__",
    "__builtins__", "__debug__", "__annotations__", "__all__", "__class__",
    "__module__", "__qualname__", "__path__", "__dict__", "__weakref__",
}

_BUILTIN_NAMES = set(dir(_builtins)) | _DUNDER_NAMES


@dataclass  # noqa: F811
class _Binding:
    lineno: int
    col: int
    kind: str  # assign/ann/aug/def/param/import/for/with/except/walrus/unpack
    reportable: bool


@dataclass
class _Use:
    lineno: int
    col: int


class _Scope:
    def __init__(self, kind: str, parent: Optional["_Scope"] = None):
        self.kind = kind  # module/function/class/lambda/comprehension
        self.parent = parent
        self.bindings: Dict[str, List[_Binding]] = {}
        self.uses: Dict[str, List[_Use]] = {}
        self.resolved_used: Set[str] = set()
        self.globals_decl: Set[str] = set()
        self.nonlocal_decl: Set[str] = set()

    def bind(self, name: str, lineno: int, col: int, kind: str, reportable: bool) -> None:
        if not name:
            return
        if name.startswith("_") or kind in ("param", "import", "with", "except"):
            reportable = False
        self.bindings.setdefault(name, []).append(
            _Binding(lineno, col, kind, reportable)
        )

    def record_use(self, name: str, lineno: int, col: int) -> None:
        self.uses.setdefault(name, []).append(_Use(lineno, col))


class _ScopeAnalyzer(ast.NodeVisitor):
    """一趟遍历：构建作用域树、绑定与使用。"""

    def __init__(self) -> None:
        self.module_scope = _Scope("module")
        self.scope = self.module_scope
        self.all_scopes: List[_Scope] = [self.module_scope]

    # ------------------------------------------------------------------ 工具
    def _push(self, kind: str) -> None:
        self.scope = _Scope(kind, parent=self.scope)
        self.all_scopes.append(self.scope)

    def _pop(self) -> None:
        assert self.scope.parent is not None
        self.scope = self.scope.parent

    def _bind_name(
        self, name: str, node: ast.AST, kind: str, reportable: bool = True
    ) -> None:
        scope = self.scope
        if (kind == "assign" or kind == "def") and scope.kind == "function":
            if name in scope.globals_decl:
                scope = self.module_scope
            elif name in scope.nonlocal_decl:
                scope = self._nearest_function_scope()
        if kind == "walrus":
            # PEP572：海象赋值绑定到最近的函数/模块作用域（推导式内也如此）
            s = self.scope
            while s is not None and s.kind == "comprehension":
                s = s.parent
            if s is not None:
                scope = s
        scope.bind(name, getattr(node, "lineno", 0) or 0, getattr(node, "col_offset", 0) or 0, kind, reportable)

    def _nearest_function_scope(self) -> _Scope:
        s = self.scope
        while s is not None and s.kind not in ("function", "module"):
            s = s.parent
        return s or self.module_scope

    def _bind_targets(self, target: ast.AST, kind: str = "assign", reportable: bool = True) -> None:
        """绑定赋值目标（支持解包）。"""
        if isinstance(target, ast.Name):
            self._bind_name(target.id, target, kind, reportable)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._bind_targets(elt, kind, reportable)
        elif isinstance(target, ast.Starred):
            self._bind_targets(target.value, kind, reportable)

    # ------------------------------------------------------------------ 作用域
    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            self.visit(stmt)

    def _visit_function(self, node: ast.AST) -> None:
        assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        self._bind_name(node.name, node, "def")
        for dec in node.decorator_list:  # 装饰器/默认值/注解在定义处（外层）求值
            self.visit(dec)
        args = node.args
        for d in list(args.defaults) + [d for d in args.kw_defaults if d is not None]:
            self.visit(d)
        if node.returns is not None:
            self.visit(node.returns)
        all_args = (
            list(args.posonlyargs) + list(args.args) + [args.vararg] + list(args.kwonlyargs)
            + [args.kwarg]
        )
        ann_scope = self.scope
        for a in all_args:
            if a is not None and a.annotation is not None:
                self.visit(a.annotation)  # 参数注解在外层作用域求值
        self._push("function")
        for a in all_args:
            if a is not None:
                self._bind_name(a.arg, a, "param", reportable=False)
        for stmt in node.body:
            self.visit(stmt)
        self._pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for d in node.args.defaults:
            self.visit(d)
        self._push("lambda")
        for a in list(node.args.args) + [node.args.vararg] + list(node.args.kwonlyargs) + [node.args.kwarg]:
            if a is not None:
                self._bind_name(a.arg, a, "param", reportable=False)
        self.visit(node.body)
        self._pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._bind_name(node.name, node, "def")
        for dec in node.decorator_list:
            self.visit(dec)
        for b in node.bases:
            self.visit(b)
        for kw in node.keywords:
            self.visit(kw)
        self._push("class")
        for stmt in node.body:
            self.visit(stmt)
        self._pop()

    # ------------------------------------------------------------------ 绑定
    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for t in node.targets:
            self._bind_targets(t)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
            self._bind_targets(node.target, "ann")
        else:
            self._bind_targets(node.target, "ann", reportable=False)  # 纯标注声明不报

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        self._bind_targets(node.target, "aug")
        if isinstance(node.target, ast.Name):  # 增强赋值同时是读操作
            self.scope.record_use(node.target.id, node.target.lineno, node.target.col_offset)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        self._bind_targets(node.target, "for")
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    visit_AsyncFor = visit_For

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind_targets(item.optional_vars, "with", reportable=False)
        for stmt in node.body:
            self.visit(stmt)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self._bind_name(node.name, node, "except", reportable=False)
        for stmt in node.body:
            self.visit(stmt)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            self._bind_name(bound, node, "import", reportable=False)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            self._bind_name(alias.asname or alias.name, node, "import", reportable=False)

    def visit_Global(self, node: ast.Global) -> None:
        self.scope.globals_decl |= set(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.scope.nonlocal_decl |= set(node.names)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self._bind_targets(node.target, "walrus")

    # ------------------------------------------------------------------ 使用
    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.scope.record_use(node.id, node.lineno, node.col_offset)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.visit(node.value)  # 只分析根对象，如 os.path 只记录 os 的使用

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self.visit(node.value)
        self.visit(node.slice)

    def visit_Delete(self, node: ast.Delete) -> None:
        for t in node.targets:  # del 视为使用（保守，避免误报）
            self.visit(t)

    # ------------------------------------------------------------------ 推导式
    def _visit_comprehension(self, node: ast.AST, gen_nodes, result) -> None:
        self._push("comprehension")
        first = True
        for gen in gen_nodes:
            if first:
                outer = self.scope
                self.scope = outer.parent or outer  # 第一个 iterable 在外层求值
                self.visit(gen.iter)
                self.scope = outer
                first = False
            else:
                self.visit(gen.iter)
            self._bind_targets(gen.target, "for", reportable=False)
            for if_ in gen.ifs:
                self.visit(if_)
        self.visit(result)
        self._pop()

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node, node.generators, node.elt)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node, node.generators, node.elt)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node, node.generators, node.elt)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node, node.generators, (node.key, node.value))

    # ------------------------------------------------------------------ 模式匹配（3.10+）
    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)
        for case in node.cases:
            self._bind_pattern(case.pattern)
            if case.guard is not None:
                self.visit(case.guard)
            for stmt in case.body:
                self.visit(stmt)

    def _bind_pattern(self, pattern: ast.pattern) -> None:
        if isinstance(pattern, ast.MatchAs):
            if pattern.pattern is not None:
                self._bind_pattern(pattern.pattern)
            if pattern.name:
                self._bind_name(pattern.name, pattern, "for")
        elif isinstance(pattern, ast.MatchStar):
            if pattern.name:
                self._bind_name(pattern.name, pattern, "for")
        elif isinstance(pattern, ast.MatchMapping):
            for p in pattern.patterns:
                self._bind_pattern(p)
            if pattern.rest:
                self._bind_name(pattern.rest, pattern, "for")
        elif isinstance(pattern, ast.MatchClass):
            self.visit(pattern.cls)  # 类名是使用
            for p in pattern.patterns:
                self._bind_pattern(p)
            for p in pattern.kwd_patterns:
                self._bind_pattern(p)
        elif isinstance(pattern, ast.MatchSequence):
            for p in pattern.patterns:
                self._bind_pattern(p)
        elif isinstance(pattern, ast.MatchValue):
            self.visit(pattern.value)


def _resolve_uses(all_scopes: List[_Scope]) -> Set[Tuple[int, int, str]]:
    """解析所有使用：返回无法解析到任何绑定/builtin 的 (lineno, col, name) 集合。

    名字解析遵循 Python 运行时语义：
    - 函数/lambda/推导式作用域向上解析时跳过 class 作用域（方法体内看不到类属性）；
    - class/module 作用域自身的表达式可以看到 class 作用域的绑定。
    """
    undefined: Set[Tuple[int, int, str]] = set()
    module_scope = all_scopes[0]
    for scope in all_scopes:
        for name, uses in scope.uses.items():
            s: Optional[_Scope] = scope
            resolved = False
            while s is not None:
                if s.kind == "class" and scope.kind not in ("module", "class"):
                    s = s.parent  # 方法与推导式看不到类作用域
                    continue
                if name not in s.globals_decl and name not in s.nonlocal_decl and name in s.bindings:
                    s.resolved_used.add(name)
                    resolved = True
                    break
                if s is module_scope:
                    break
                s = s.parent
            if not resolved:
                if name in _BUILTIN_NAMES:
                    continue
                for (ln, col) in [(u.lineno, u.col) for u in uses]:
                    undefined.add((ln, col, name))
    return undefined


@register("unused-variable")  # noqa: F821
class UnusedVariableRule(BaseRule):
    category = "规范"
    default_severity = "warning"
    description = "变量声明或赋值后从未被引用（仅检查函数局部作用域，遵循 pyflakes 语义）"

    def check(self, ctx: RuleContext) -> List[Issue]:
        assert ctx.tree is not None
        analyzer = _ScopeAnalyzer()
        analyzer.visit(ctx.tree)
        all_scopes = analyzer.all_scopes
        _resolve_uses(all_scopes)
        issues: List[Issue] = []
        for scope in all_scopes:
            if scope.kind != "function":
                continue
            for name, bindings in scope.bindings.items():
                if name in scope.resolved_used:
                    continue
                for b in bindings:
                    if b.reportable:
                        issues.append(
                            self.make_issue(
                                ctx,
                                b.lineno,
                                f"变量 `{name}` 声明后未被使用",
                                column=b.col + 1,
                                suggestion=_UNUSED_SUGGESTION,
                            )
                        )
        return issues


@register("undefined-variable")  # noqa: F821
class UndefinedVariableRule(BaseRule):
    category = "逻辑"
    default_severity = "error"
    description = "引用了未定义的变量（作用域链解析失败且不属于内置名称）"

    def check(self, ctx: RuleContext) -> List[Issue]:
        assert ctx.tree is not None
        analyzer = _ScopeAnalyzer()
        analyzer.visit(ctx.tree)
        undefined = _resolve_uses(analyzer.all_scopes)
        issues: List[Issue] = []
        seen: Set[Tuple[int, int]] = set()
        for (ln, col, name) in sorted(undefined):
            key = (ln, col)
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                self.make_issue(
                    ctx,
                    ln,
                    f"引用了未定义的变量 `{name}`",
                    column=col + 1,
                    suggestion=_UNDEFINED_SUGGESTION,
                )
            )
        return issues
