"""
测试用例 10 - 场景规则（批改场景）
预期检测：
- 通用场景：无问题
- 批改场景：第7行 warning (函数名不符合批改场景命名约定)
说明：此测试假设"批改场景"要求评分相关函数必须以 score_ 或 grade_ 开头
"""

def calculate_result(answer, reference):  # 第7行：批改场景应命名为 score_* 或 grade_*
    """计算批改结果"""
    if answer == reference:
        return 100
    else:
        return 0

def grade_submission(student_id, score):
    """记录学生成绩（符合批改场景规范）"""
    return {
        "student_id": student_id,
        "score": score,
        "status": "graded"
    }
