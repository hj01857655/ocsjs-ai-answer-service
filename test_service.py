# -*- coding: utf-8 -*-
"""
测试脚本
用于测试AI题库服务是否正常工作
"""
import requests
import json
import sys
import os

# 读取配置文件
def load_config():
    """加载配置文件"""
    config_file = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"读取配置文件出错: {str(e)}")
    return {}

# 加载配置
config = load_config()

# 服务URL
host = config.get('service', {}).get('host', '0.0.0.0')
port = config.get('service', {}).get('port', 5000)
SERVICE_URL = f"http://{host}:{port}"

def test_health():
    """测试健康检查接口"""
    print("测试健康检查接口...")
    try:
        response = requests.get(f"{SERVICE_URL}/api/health")
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        print("健康检查接口测试成功！\n")
        return True
    except Exception as e:
        print(f"健康检查接口测试失败: {str(e)}")
        return False

def test_search(question, question_type=None, options=None):
    """测试搜索接口"""
    print(f"测试搜索接口: {question}")
    
    params = {
        "title": question
    }
    
    if question_type:
        params["type"] = question_type
        
    if options:
        params["options"] = options
    
    try:
        print("发送请求...")
        print(f"参数: {json.dumps(params, indent=2, ensure_ascii=False)}")
        
        response = requests.get(f"{SERVICE_URL}/api/search", params=params)
        
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应内容: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if result.get("code") == 1:
            print("搜索接口测试成功！\n")
            return True
        else:
            print(f"搜索接口测试失败: {result.get('msg', '未知错误')}\n")
            return False
    except Exception as e:
        print(f"搜索接口测试失败: {str(e)}\n")
        return False

def main():
    """主测试函数"""
    print("=" * 50)
    print("AI题库服务测试脚本")
    print("=" * 50)
    
    # 测试健康检查接口
    if not test_health():
        print("健康检查失败，请确认服务是否正常运行。")
        sys.exit(1)
    
    # 测试单选题
    test_search(
        "中国的首都是哪个城市？", 
        "single",
        "A. 上海\nB. 北京\nC. 广州\nD. 深圳"
    )
    
    # 测试多选题
    test_search(
        "以下哪些是中国的一线城市？", 
        "multiple",
        "A. 北京\nB. 上海\nC. 广州\nD. 深圳\nE. 成都\nF. 杭州"
    )
    
    # 测试判断题
    test_search(
        "地球是太阳系中第三颗行星。", 
        "judgement"
    )
    
    # 测试填空题
    test_search(
        "《红楼梦》的作者是_______。", 
        "completion"
    )
    
    print("=" * 50)
    print("测试完成！")
    print("=" * 50)

if __name__ == "__main__":
    main()