"""
测试用例 08 - 缺陷：unbalanced-bracket
预期检测：第8行 error
"""

def format_message(name, age):
    """格式化消息"""
    message = f"用户 {name} 年龄 {age"  # 第8行：缺少闭合的 }
    return message

if __name__ == "__main__":
    print(format_message("Alice", 25))
