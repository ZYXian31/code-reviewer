"""
测试用例 11 - 缺陷：prefer-orjson
预期检测：第6行 warning（import json）、第11行 warning（json.loads）、第16行 warning（json.dumps）
说明：应使用高性能的 orjson 替代标准库 json
"""
import json  # 第6行：应使用 orjson

def load_config(config_str: str) -> dict:
    """解析配置字符串"""
    # 第11行：应使用 orjson.loads
    return json.loads(config_str)

def save_result(data: dict) -> str:
    """序列化结果"""
    # 第16行：应使用 orjson.dumps
    return json.dumps(data, ensure_ascii=False)

if __name__ == "__main__":
    cfg = load_config('{"name": "test"}')
    print(save_result(cfg))
