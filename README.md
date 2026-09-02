# 面向特定场景的代码评审工具（2026 校招 AI 提效小作业）

基于 **AST 静态分析** 的代码评审工具，完整工作链路：
`代码导入 → 语法解析(AST) → 规则检查 → 问题定位与分级 → 结构化报告输出`
支持按业务场景加载不同规则集，规则全部配置化管理。

## 快速开始

环境要求：Python 3.9+（纯标准库实现，**零第三方依赖**；开发测试可另装 playwright/pytest，不影响运行）。

```bash
# 1. 评审单个文件（输出 JSON / Markdown / HTML 到 reports/）
python3 -m code_reviewer path/to/file.py

# 2. 批量评审目录（递归遍历 *.py）
python3 -m code_reviewer --output-dir reports/testset code_review_testcases/

# 3. 场景切换：批改场景（在通用规则上叠加场景专属规则）
python3 -m code_reviewer -s grading code_review_testcases/test_case_10_scenario_rule.py

# 4. 从标准输入评审一段代码
echo 'if x = 100:' | python3 -m code_reviewer --stdin

# 5. 查看规则清单 / 全量回归测试
python3 -m code_reviewer --list-rules
python3 -m unittest discover -s tests          # 55 个单元+集成测试
python3 scripts/run_all_tests.py --compare      # 跑作业测试集并对比标准答案

# 6. 评审后上传 i 讯飞云文档（需先填写 config/upload.json）
python3 -m code_reviewer code/ --upload --upload-title "代码评审报告-20260825"
```

## 内置规则（9 条，全部可配置启停/分级）

| 规则名称 | 类别 | 严重程度 | 触发条件 |
| --- | --- | --- | --- |
| assign-in-condition | 语法严重错误 | error | 条件判断中使用赋值运算符而非比较运算符（如 `if A = B`） |
| syntax-error | 语法严重错误 | error | AST 解析失败的其他严重语法错误（兜底） |
| unbalanced-bracket | 语法严重错误 | error | 括号不匹配（含 f-string 缺少闭合 `}`） |
| undefined-variable | 逻辑 | error | 引用了未定义的变量 |
| unused-variable | 规范 | warning | 变量声明或赋值后从未被引用（函数局部作用域） |
| bare-except | 规范 | warning | 使用裸 `except:` 未指定异常类型 |
| prefer-orjson | 性能 | warning | 使用标准库 json 而非高性能 orjson |
| unused-import | 规范 | info | 导入的模块/符号未被使用 |
| scenario-rule | 特定场景 | warning | 违反当前业务场景加载的专属规则（参数由场景配置决定） |

每个问题均输出：**行号、列号、严重程度、规则名称、问题描述、修复建议、源码片段**。

## 项目结构

```
.
├── code_reviewer/            # 工具包
│   ├── __main__.py / cli.py  # 命令行入口（单文件/目录/stdin/多格式/上传）
│   ├── engine.py             # 评审引擎（解析→规则编排→分级→汇总）
│   ├── models.py             # Issue/FileReview/Report 数据模型
│   ├── config.py             # 规则配置与场景配置加载
│   ├── formatters.py         # JSON / Markdown / HTML 报告
│   ├── uploader.py           # i 讯飞云文档上传（webhook / Lark Cli 两种模式）
│   ├── logger.py             # 日志（控制台 + 滚动文件）
│   └── rules/                # 规则包（注册表 + 6 个规则模块）
├── config/
│   ├── rules.json            # 规则启停 / 严重程度（新增/关闭规则不改代码）
│   ├── scenarios/
│   │   ├── general.json      # 通用场景（不叠加场景规则）
│   │   └── grading.json      # 批改场景（score_/grade_ 前缀命名约定）
│   └── upload.json           # 云文档上传配置模板
├── code_review_testcases/    # 作业配套测试集（11 用例 + 标准答案）
├── scripts/run_all_tests.py  # 批量评审 + 与标准答案对比（漏报/误报统计）
├── tests/                    # 55 条单元/集成测试（unittest，零依赖）
├── reports/                  # 全量评审结果（testset_general / testset_grading / full_report）
└── docs/                     # 实践报告
```

## 关键技术设计

**AST 失败恢复路径**。`if x = 100:`、f-string 缺少闭合 `}` 这类缺陷会让 `ast.parse` 直接失败，
工具自动降级：token 流扫描定位 `if/elif/while` 条件中的裸 `=`（assign-in-condition），
字符级扫描器（识别字符串/注释/f-string 前缀与转义）定位未闭合括号（unbalanced-bracket）；
两者都未命中才报通用 `syntax-error`，避免同一文件重复报告。

**作用域分析**（unused-variable / undefined-variable）。手写五类作用域（模块/函数/类/lambda/推导式），
收集绑定与使用后做名字解析，遵循 pyflakes 语义控制误报：模块级变量不报未使用、
参数/with-as/except-as/下划线变量不报、函数体解析跳过类作用域（与 Python 运行时一致）。

**配置化 + 场景化**。`config/rules.json` 控制每条规则启停与严重程度（改 JSON 即可新增/关闭规则）；
场景规则集放在 `config/scenarios/*.json`，新增场景 = 新增一个 JSON 文件，规则参数（前缀、关键词、消息）全配置驱动。

**工程健壮性**。单文件异常隔离（一个文件失败不中断批量）、UTF-8/GBK 编码自适应、
控制台+滚动文件双日志、JSON/Markdown/HTML 三种报告、`--strict` 门禁退出码。

## 测试集成绩（对比标准答案）

- **error 级漏报 = 0**（红线达标）：assign-in-condition / undefined-variable / unbalanced-bracket 全部检出
- 正例 test_case_01/02 零误报；test_case_10 场景切换（通用 0 / 批改 1 条 scenario-rule）通过
- 唯一"多报"为 `test_case_09` 中的 `import math`——标准答案遗漏该项（math 确实未使用），工具行为更准确

详见 `reports/compare_report.json` 与 `reports/full_report/review_summary.html`。

## 依赖清单

运行时零依赖（仅 Python 标准库：ast / tokenize / json / logging / argparse / urllib / webbrowser）。
开发建议：`pytest`（替代 unittest 运行测试）、`playwright`（可选，用于报告截图）。
