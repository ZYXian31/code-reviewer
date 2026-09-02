"""
测试用例 05 - 缺陷：undefined-variable
预期检测：第10行 error
"""

def calculate_total(prices, discount):
    """计算总价"""
    subtotal = sum(prices)
    
    # 错误：引用了未定义的变量 tax_rate
    total = subtotal - discount + tax_rate  # 第10行
    
    return total

if __name__ == "__main__":
    items = [100, 200, 150]
    result = calculate_total(items, 50)
    print(f"总价: {result}")
