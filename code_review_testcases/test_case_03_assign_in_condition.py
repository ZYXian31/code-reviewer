"""
测试用例 03 - 缺陷：assign-in-condition
预期检测：第9行 error
"""

def check_user_status(user_id, status):
    """检查用户状态"""
    active_users = [100, 200, 300]
    
    # 错误：条件判断中误用赋值运算符
    if user_id = 100:  # 第9行：应为 ==
        print("找到用户")
        return True
    
    return False

if __name__ == "__main__":
    check_user_status(100, "active")
