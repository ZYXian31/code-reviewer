"""
测试用例 01 - 正例（无问题）
预期结果：无 error/warning
"""
import orjson
from typing import List

def process_user_data(user_id: int, name: str) -> dict:
    """处理用户数据并返回格式化结果"""
    if user_id <= 0:
        raise ValueError("用户ID必须为正整数")
    
    result = {
        "id": user_id,
        "name": name.strip(),
        "status": "active"
    }
    
    return result

def calculate_score(scores: List[int]) -> float:
    """计算平均分"""
    if not scores:
        return 0.0
    
    total = sum(scores)
    average = total / len(scores)
    return round(average, 2)

if __name__ == "__main__":
    user = process_user_data(123, "Alice")
    print(orjson.dumps(user).decode("utf-8"))
    
    test_scores = [85, 90, 78, 92]
    avg = calculate_score(test_scores)
    print(f"平均分: {avg}")
