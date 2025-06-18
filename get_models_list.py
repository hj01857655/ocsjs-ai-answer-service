#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取第三方API服务的模型列表
"""

import requests
import json
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_models_list():
    # 从config.json读取配置
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 获取第一个激活的代理
    third_party_apis = config.get('third_party_apis', [])
    if not third_party_apis:
        print("❌ 配置文件中没有找到 third_party_apis")
        return []

    # 找到第一个激活的代理
    active_proxy = None
    for proxy in third_party_apis:
        if proxy.get('is_active', False):
            active_proxy = proxy
            break

    if not active_proxy:
        print("❌ 没有找到激活的代理")
        return []

    api_base = active_proxy['api_base']
    api_keys = active_proxy['api_keys']

    print(f"🔧 使用代理: {active_proxy['name']}")
    print(f"🔧 API基础URL: {api_base}")
    print(f"🔑 可用API密钥数量: {len(api_keys)}")

    url = f"{api_base}/v1/models"
    print(f"\n📡 请求URL: {url}")

    # 尝试多个API密钥
    for i, api_key in enumerate(api_keys[:5]):  # 最多尝试前5个密钥
        print(f"\n🔄 尝试API密钥 #{i+1}: {api_key[:20]}...")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            print("🚀 发送请求...")
            response = requests.get(url, headers=headers, timeout=30, verify=False)
            print(f"📊 状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print("✅ 成功获取模型列表！")

                # 解析模型列表
                if 'data' in data:
                    models = [model['id'] for model in data['data']]
                    print(f"\n📋 可用模型数量: {len(models)}")
                    print("📝 模型列表:")
                    for j, model in enumerate(models, 1):
                        print(f"  {j:2d}. {model}")

                    # 保存到文件
                    with open('available_models.json', 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"\n💾 完整模型信息已保存到 available_models.json")

                    return models
                else:
                    print("⚠️ 响应格式异常，没有找到模型数据")
                    print(f"响应内容: {json.dumps(data, ensure_ascii=False, indent=2)}")

            elif response.status_code == 401:
                print(f"❌ API密钥无效 (401)")
                continue  # 尝试下一个密钥
            elif response.status_code == 429:
                print(f"❌ 请求频率限制 (429)")
                continue  # 尝试下一个密钥
            else:
                print(f"❌ 请求失败 ({response.status_code})")
                print(f"响应内容: {response.text}")
                continue  # 尝试下一个密钥

        except Exception as e:
            print(f"❌ 请求异常: {str(e)}")
            continue  # 尝试下一个密钥

    print(f"\n❌ 所有API密钥都无法获取模型列表")
    return []

if __name__ == "__main__":
    models = get_models_list()

    if models:
        print(f"\n🎯 建议更新config.json中的models配置为以下可用模型:")
        print(f"\"models\": {json.dumps(models[:5], ensure_ascii=False, indent=2)}")  # 显示前5个模型作为建议
