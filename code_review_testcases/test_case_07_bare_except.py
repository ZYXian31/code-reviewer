"""
测试用例 07 - 缺陷：bare-except
预期检测：第10行 warning
"""

def read_file_content(filename):
    """读取文件内容"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            return content
    except:  # 第10行：应指定异常类型
        print("读取文件失败")
        return None

if __name__ == "__main__":
    result = read_file_content("data.txt")
    if result:
        print(result)
