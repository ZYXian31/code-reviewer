"""
测试用例 06 - 缺陷：unused-import
预期检测：第6行、第7行 info
"""
import orjson
import os  # 第6行：导入后未使用
import sys  # 第7行：导入后未使用
from typing import List

def parse_config(config_str: str) -> dict:
    """解析配置字符串"""
    return orjson.loads(config_str)

def get_items() -> List[str]:
    """获取项目列表"""
    return ["item1", "item2", "item3"]
