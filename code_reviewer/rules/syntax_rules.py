"""语法严重错误规则（含 AST 解析失败时的恢复路径）。

关键设计：`if x = 100:`、f-string 缺少闭合 `}` 等缺陷会让 ast.parse 直接失败，
此时 AST 规则不可用。工具自动降级为"源码语义恢复"路径：
1. token 流扫描 → assign-in-condition（条件判断中误用赋值运算符 =）；
2. 字符级括号/f-string 扫描 → unbalanced-bracket（括号不匹配）；
3. 两者都未命中时 → syntax-error 兜底（报告原始语法错误与位置）。

这样既保证 error 级问题不漏报（红线），又避免同一文件重复报"通用语法错误"。
"""

from __future__ import annotations

import io
import tokenize
from typing import List, Optional, Tuple

from .base import BaseRule, RuleContext, register
from ..models import Issue

_ASSIGN_SUGGESTION = (
    "将赋值运算符 = 改为比较运算符 ==；条件判断中不能直接赋值，"
    "若确实需要赋值请使用海象运算符 := 或拆分语句"
)
_BRACKET_SUGGESTION = "补全缺失的闭合括号，或检查是否存在未闭合的 f-string 表达式"


@register("assign-in-condition")  # noqa: F821 - 依赖 rules/__init__.py 导入注册
class AssignInConditionRule(BaseRule):
    category = "语法严重错误"
    default_severity = "error"
    description = "条件判断中使用赋值运算符而非比较运算符，如 if A = B（真实缺陷会导致 SyntaxError，需在恢复路径中识别）"

    def check(self, ctx: RuleContext) -> List[Issue]:
        issues: List[Issue] = []
        if ctx.parse_error is None:
            return issues  # 正常解析的文件不可能是这种写法（语法错误）
        tokens: List[tokenize.TokenInfo] = []
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(ctx.source).readline))
        except (tokenize.TokenError, SyntaxError, IndentationError):
            return issues  # tokenize 自身失败时交给其它规则
        depth = 0
        cond_kw_pos: Optional[Tuple[int, int]] = None  # (line, col) 最近的 if/elif/while
        for idx, t in enumerate(tokens):
            if t.type == tokenize.OP:
                s = t.string
                if s in "([{":
                    depth += 1
                elif s in ")]}":
                    depth = max(depth - 1, 0)
                elif s == "=" and depth == 0 and cond_kw_pos is not None:
                    prev = tokens[idx - 1] if idx > 0 else None
                    if prev is not None and prev.string == ":":
                        continue  # 防护：理论上 := 是独立 token，此处再兜底一次
                    issues.append(
                        self.make_issue(
                            ctx,
                            t.start[0],
                            "条件判断中疑似误用赋值运算符 `=`，应为 `==`",
                            column=t.start[1] + 1,
                            suggestion=_ASSIGN_SUGGESTION,
                        )
                    )
                elif s == ":":
                    cond_kw_pos = None  # 条件结束
            elif t.type == tokenize.NAME:
                if t.string in ("if", "elif", "while") and depth == 0:
                    cond_kw_pos = (t.start[0], t.start[1])
                elif t.string in ("def", "class", "return", "import", "from", "raise"):
                    cond_kw_pos = None
            elif t.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
                cond_kw_pos = None
        return issues


# ---------------------------------------------------------------------------
# 括号匹配扫描器（工作在原始源码上，不依赖 AST/tokenize）
# ---------------------------------------------------------------------------

_MATCH = {"(": ")", "[": "]", "{": "}"}


def _scan_unbalanced(src: str) -> Tuple[List[Issue], Optional[str]]:
    """字符级扫描。

    Returns: (issues, 未闭合字符串信息或 None)。
    issues 的 rule 为 "unbalanced-bracket"，position 为未闭合括号的位置。
    """
    n = len(src)
    i, line, col = 0, 1, 1
    stack: List[Tuple[str, int, int]] = []  # 全局代码括号 (char, line, col)
    unmatched_list: List[Tuple[int, int]] = []  # global 未闭合括号位置（只保留最外层）

    def consume_string(start: int) -> Tuple[int, int, int, List[Tuple[int, int]], bool, str]:
        """从 start（指向引号）消费一个字符串字面量。

        Returns: (new_i, new_line, new_col, fstack, closed, opener_char)
        fstack: f-string 内部未闭合 '{' 的位置列表。
        """
        j = start - 1
        while j >= 0 and (src[j].isalpha() or src[j] == "_"):
            j -= 1
        prefix = src[j + 1 : start]
        is_f = "f" in prefix.lower()
        quote = src[start]
        triple = src[start : start + 3] == quote * 3
        k = start + (3 if triple else 1)
        ln, cl = line, col + (3 if triple else 1)
        fstack: List[Tuple[int, int]] = []
        while k < n:
            ch = src[k]
            if ch == "\\":
                k += 2
                cl += 2
                continue
            if ch == "\n":
                if not triple:
                    break  # 单行字符串异常中断（词法错误）
                k += 1
                ln += 1
                cl = 1
                continue
            if is_f:
                if ch == "{" and src[k : k + 2] != "{{":
                    fstack.append((ln, cl))
                elif ch == "}" and src[k : k + 2] != "}}":
                    if fstack:
                        fstack.pop()
                # f-string 的内层引号在 3.10 词法下总是字符串终止符；
                # 若此时 fstack 非空，说明表达式未闭合（如 f"用户 {age"），
                # 交由主循环把 fstack 残留报告为 unbalanced-bracket
                if ch == quote:
                    return k + 1, ln, cl + 1, fstack, True, quote
            else:
                if triple and src[k : k + 3] == quote * 3:
                    return k + 3, ln, cl + 3, fstack, True, quote
                if ch == quote:
                    return k + 1, ln, cl + 1, fstack, True, quote
            k += 1
            cl += 1
        return k, ln, cl, fstack, False, quote

    while i < n:
        c = src[i]
        if c == "\n":
            i += 1
            line += 1
            col = 1
            continue
        if c == "#":
            while i < n and src[i] != "\n":
                i += 1
                col += 1
            continue
        if c in ("'", '"'):
            new_i, new_line, new_col, fstack, closed, _ = consume_string(i)
            for fl, fc in fstack:
                # f-string 内部未闭合的 '{'：每个都值得报告第一个（最外层）
                unmatched_list.append((fl, fc))
            i, line, col = new_i, new_line, new_col
            continue
        if c in "([{":
            stack.append((c, line, col))
            i += 1
            col += 1
            continue
        if c in ")]}":
            if stack and _MATCH.get(stack[-1][0]) == c:
                stack.pop()
            i += 1
            col += 1
            continue
        i += 1
        col += 1

    issues: List[Issue] = []
    if stack:
        ch, ln, cl = stack[0]  # 最外层未闭合括号
        issues.append((ln, cl, _MATCH[ch]))
    if unmatched_list:
        ln, cl = unmatched_list[0]
        issues.append((ln, cl, "}"))
    return issues, None


@register("unbalanced-bracket")  # noqa: F821
class UnbalancedBracketRule(BaseRule):
    category = "语法严重错误"
    default_severity = "error"
    description = "括号不匹配（如 f-string 缺少闭合的 }、花括号/方括号/圆括号未闭合）"

    def check(self, ctx: RuleContext) -> List[Issue]:
        issues: List[Issue] = []
        if ctx.parse_error is None:
            return issues
        scan, _ = _scan_unbalanced(ctx.source)
        for (ln, cl, missing) in scan:
            issues.append(
                self.make_issue(
                    ctx,
                    ln,
                    f"括号不匹配，缺少闭合的 `{missing}`",
                    column=cl,
                    suggestion=_BRACKET_SUGGESTION,
                )
            )
        return issues


@register("syntax-error")  # noqa: F821
class SyntaxErrorRule(BaseRule):
    category = "语法严重错误"
    default_severity = "error"
    description = "AST 解析失败的其他严重语法错误（兜底规则）"

    def check(self, ctx: RuleContext) -> List[Issue]:
        if ctx.parse_error is None:
            return []
        e = ctx.parse_error
        lineno = getattr(e, "lineno", None) or 1
        msg = getattr(e, "msg", None) or str(e)
        return [
            self.make_issue(
                ctx,
                int(lineno),
                f"语法错误，无法解析：{msg}",
                suggestion="修复语法错误后重新运行评审",
            )
        ]
