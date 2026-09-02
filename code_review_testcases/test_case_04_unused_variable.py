"""
测试用例 04 - 缺陷：unused-variable
预期检测：第8行、第15行 warning
"""

def process_data(input_list):
    """处理数据"""
    result = []
    temp_value = 0  # 第8行：声明后未使用
    
    for item in input_list:
        if item > 10:
            result.append(item * 2)
    
    # 第15行：赋值后未使用
    final_count = len(result)
    
    return result

if __name__ == "__main__":
    data = [5, 12, 8, 20, 15]
    output = process_data(data)
    print(output)
