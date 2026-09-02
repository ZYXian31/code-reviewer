"""code_reviewer - 面向特定场景的静态代码评审工具。

工作链路：代码导入 → 语法解析(AST) → 规则检查 → 问题定位与分级 → 结构化报告输出。
基于 AST 实现规则检查（AST 解析失败时自动降级为 token/源码扫描恢复路径），
规则全部配置化管理（config/rules.json 控制启停与分级，config/scenarios/ 定义场景规则集）。
"""

__version__ = "1.0.0"
__tool_name__ = "code-reviewer"
