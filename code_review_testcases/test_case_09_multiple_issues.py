"""
测试用例 09 - 综合：多个问题
预期检测：
- 第7行 info (unused-import)
- 第11行 warning (unused-variable)
- 第16行 error (undefined-variable)
"""
import math
import random  # 第7行：未使用

def complex_calculation(x, y):
    """复杂计算"""
    temp = x + y  # 第11行：声明后未使用
    
    # 错误：使用了未定义的变量
    result = x * y + unknown_var  # 第16行
    
    return result

if __name__ == "__main__":
    print(complex_calculation(10, 20))
