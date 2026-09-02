# 代码评审工具测试用例集

## 概述

本测试集用于验证代码评审工具的检查能力，包含10个Python测试文件和1份标准答案。

## 文件清单

### 测试文件（10个）

| 文件 | 类型 | 包含的缺陷 | 预期检出数 |
|------|------|-----------|----------|
| test_case_01_correct.py | 正例 | 无 | 0 |
| test_case_02_correct.py | 正例 | 无 | 0 |
| test_case_03_assign_in_condition.py | 反例 | assign-in-condition | 1 error |
| test_case_04_unused_variable.py | 反例 | unused-variable | 2 warning |
| test_case_05_undefined_variable.py | 反例 | undefined-variable | 1 error |
| test_case_06_unused_import.py | 反例 | unused-import | 2 info |
| test_case_07_bare_except.py | 反例 | bare-except | 1 warning |
| test_case_08_unbalanced_bracket.py | 反例 | unbalanced-bracket | 1 error |
| test_case_09_multiple_issues.py | 反例 | 多个问题 | 1 error + 1 warning + 1 info |
| test_case_10_scenario_rule.py | 场景规则 | scenario-rule（批改场景） | 通用场景0，批改场景1 warning |
| test_case_11_prefer_orjson.py | 反例 | prefer-orjson | 3 warning |

### 标准答案

- `expected_results.json`：包含每个测试用例的预期检出结果（行号、规则名、严重程度、信息描述）

## 使用方法

### 1. 运行工具评审所有测试文件

```bash
# 假设你的工具命令为 code_reviewer
for file in test_case_*.py; do
    echo "=== 评审 $file ==="
    code_reviewer "$file" --output "${file%.py}_result.json"
done
```

### 2. 对比实际输出与标准答案

将工具输出的结果与 `expected_results.json` 对比：

- **漏报检查**：标准答案中的每个 error 级问题都必须被检出
- **误报检查**：工具报告的问题应在合理范围内（允许≤2个 info/warning 级误报）
- **行号精度**：允许±1行偏差（考虑不同AST实现的行号计数差异）

### 3. 场景切换测试

对于 `test_case_10_scenario_rule.py`：

```bash
# 通用场景：应无问题
code_reviewer test_case_10_scenario_rule.py --scenario general

# 批改场景：应检出第7行 warning
code_reviewer test_case_10_scenario_rule.py --scenario grading
```

## 评分依据

根据作业评分标准，本测试集用于"检查准确性"维度的打分（满分20分）：

| 档次 | 分数 | 判定条件 |
|------|------|---------|
| 优 | 17-20 | error级0漏报，误报≤1，行号准确 |
| 良 | 12-16 | error级0漏报，误报2-3个，行号基本准确 |
| 及格 | 7-11 | error级漏报1个，或误报较多（4-6个） |
| 差 | 0-6 | error级漏报≥2个，或误报严重（>6个） |

**关键红线**：`test_case_03`、`test_case_05`、`test_case_08` 的 error 级问题必须全部检出，否则不得评为"优"。

## 注意事项

1. **正例的重要性**：test_case_01 和 test_case_02 不应报任何问题，若工具误报则说明规则过于严格或误判。

2. **语法错误的特殊性**：test_case_03 和 test_case_08 包含真实的语法错误（无法通过 Python 解释器），工具必须能捕获这类"会导致代码无法运行"的严重问题。

3. **场景规则的灵活性**：test_case_10 的检出结果依赖场景配置，评委需确认工具是否支持场景切换。

4. **标准答案的行号**：JSON 中的行号是基于文件编写时的位置，若测试文件被修改，需同步更新标准答案。

## 测试集统计

- 总文件数：11
- 正例：2（18%）
- 反例：9（82%）
- 总预期问题数：16（通用场景）+ 1（批改场景额外）
  - error 级：4
  - warning 级：8
  - info 级：4

涵盖规则：9条基线规则全覆盖（含 prefer-orjson）。
