"""
测试用例 02 - 正例（场景规则-批改场景）
预期结果：无 error/warning（假设当前为"通用"场景）
"""

def validate_answer(student_answer: str, correct_answer: str) -> bool:
    """验证学生答案是否正确"""
    try:
        normalized_student = student_answer.strip().lower()
        normalized_correct = correct_answer.strip().lower()
        return normalized_student == normalized_correct
    except AttributeError as e:
        print(f"答案格式错误: {e}")
        return False

def calculate_similarity(text1: str, text2: str) -> float:
    """计算文本相似度（简化版）"""
    if not text1 or not text2:
        return 0.0
    
    set1 = set(text1.lower().split())
    set2 = set(text2.lower().split())
    
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    
    return intersection / union if union > 0 else 0.0
