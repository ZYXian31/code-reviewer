"""配置加载：规则启停/分级配置（rules.json）与场景规则集（scenarios/*.json）。

设计目标（作业要求）：规则配置化管理，支持新增/关闭规则、调整严重程度，
无需修改核心代码即可扩展。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .models import SEVERITIES

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RULES_CONFIG = os.path.join(REPO_ROOT, "config", "rules.json")
DEFAULT_SCENARIOS_DIR = os.path.join(REPO_ROOT, "config", "scenarios")


class ConfigError(Exception):
    """配置解析错误。"""


def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"配置文件不存在: {path}")
    except json.JSONDecodeError as e:
        raise ConfigError(f"配置文件不是合法 JSON ({path}): {e}")
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件顶层必须是对象: {path}")
    return data


class RulesConfig:
    """规则配置：控制每条规则的启用状态与严重程度覆盖。

    格式示例（config/rules.json）:
        {
          "version": "1.0",
          "rules": {
            "unused-variable": {"enabled": true, "severity": "warning"},
            "prefer-orjson":   {"enabled": true, "severity": "info"}
          }
        }
    """

    def __init__(self, data: Dict[str, Any]):
        self.version = data.get("version", "1.0")
        raw_rules = data.get("rules", {})
        if not isinstance(raw_rules, dict):
            raise ConfigError("rules.json 中 'rules' 必须是对象")
        self.enabled: Dict[str, bool] = {}
        self.severity_overrides: Dict[str, str] = {}
        for name, cfg in raw_rules.items():
            if isinstance(cfg, bool):  # 简化写法:  "rule-name": true/false
                self.enabled[name] = cfg
                continue
            if not isinstance(cfg, dict):
                raise ConfigError(f"规则 {name} 的配置必须是对象或布尔值")
            self.enabled[name] = bool(cfg.get("enabled", True))
            sev = cfg.get("severity")
            if sev is not None:
                if sev not in SEVERITIES:
                    raise ConfigError(f"规则 {name} 的 severity 非法: {sev}")
                self.severity_overrides[name] = sev

    @classmethod
    def load(cls, path: Optional[str] = None) -> "RulesConfig":
        return cls(_load_json(path or DEFAULT_RULES_CONFIG))

    def is_enabled(self, rule_name: str) -> bool:
        return self.enabled.get(rule_name, True)

    def severity_for(self, rule_name: str, default: str) -> str:
        return self.severity_overrides.get(rule_name, default)


class ScenarioConfig:
    """场景规则集配置。

    通用场景（general）不加载任何额外规则；其他场景在通用规则（AST 基线规则）之上
    叠加场景专属规则。支持新增场景：在 config/scenarios/ 下新增 JSON 文件即可。

    格式示例（config/scenarios/grading.json）:
        {
          "name": "grading",
          "description": "批改/评分场景",
          "rules": [
            {"rule": "scenario-rule", "params": {"required_prefixes": ["score_", "grade_"], ...}}
          ]
        }
    """

    def __init__(self, data: Dict[str, Any], path: Optional[str] = None):
        self.name: str = data.get("name", os.path.splitext(os.path.basename(path or ""))[0] or "general")
        self.description: str = data.get("description", "")
        self.extra_rules: List[Dict[str, Any]] = list(data.get("rules", []))
        self.path = path

    @classmethod
    def load(cls, name: str, scenarios_dir: Optional[str] = None) -> "ScenarioConfig":
        """按场景名称加载；name 也可以是自定义 JSON 文件路径。"""
        if name == "general":
            return cls({"name": "general", "description": "通用场景（无场景专属规则）"})
        if os.path.isfile(name):
            path = name
        else:
            d = scenarios_dir or DEFAULT_SCENARIOS_DIR
            path = os.path.join(d, f"{name}.json")
            if not os.path.isfile(path):
                raise ConfigError(
                    f"未找到场景配置: {path}（请使用内置场景 general/grading，或提供自定义 JSON 路径）"
                )
        return cls(_load_json(path), path=path)


__all__ = [
    "ConfigError",
    "RulesConfig",
    "ScenarioConfig",
    "DEFAULT_RULES_CONFIG",
    "DEFAULT_SCENARIOS_DIR",
]
