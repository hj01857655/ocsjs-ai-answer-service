#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速并发模型测试脚本
使用多线程快速测试第三方代理池中的所有模型
支持流式和非流式响应测试
"""

import requests
import json
import time
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class FastModelTester:
    def __init__(self, api_base: str, api_keys: list):
        self.api_base = api_base.rstrip('/')
        self.api_keys = api_keys
        self.key_index = 0
        self.lock = threading.Lock()

        # 结果分类
        self.stream_models = []
        self.non_stream_models = []
        self.failed_models = []

    def get_api_key(self):
        """线程安全获取API密钥"""
        with self.lock:
            key = self.api_keys[self.key_index]
            self.key_index = (self.key_index + 1) % len(self.api_keys)
            return key

    def quick_test_model(self, model_info):
        """快速测试单个模型"""
        model, index, total = model_info

        # 先测试流式
        stream_result = self.test_stream(model)
        if stream_result['success']:
            print(f"[{index:2d}/{total}] ✅ {model[:40]}... 流式({stream_result['time']:.1f}s)")
            return {'type': 'stream', 'model': model, 'result': stream_result}

        # 再测试非流式
        non_stream_result = self.test_non_stream(model)
        if non_stream_result['success']:
            print(f"[{index:2d}/{total}] ✅ {model[:40]}... 非流式({non_stream_result['time']:.1f}s)")
            return {'type': 'non_stream', 'model': model, 'result': non_stream_result}

        # 都失败
        error = stream_result.get('error', 'Unknown')[:15]
        print(f"[{index:2d}/{total}] ❌ {model[:40]}... {error}")
        return {'type': 'failed', 'model': model, 'result': stream_result}

    def test_stream(self, model):
        """测试流式响应"""
        try:
            response = requests.post(
                f"{self.api_base}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.get_api_key()}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "1+1=?"}],
                    "max_tokens": 10,
                    "temperature": 0,
                    "stream": True
                },
                stream=True,
                timeout=6,
                verify=False
            )

            start_time = time.time()

            if response.status_code == 200:
                content = ""
                for line in response.iter_lines():
                    if line and line.decode('utf-8').startswith('data: '):
                        data_str = line.decode('utf-8')[6:]
                        if data_str.strip() == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            if 'choices' in data and data['choices']:
                                delta = data['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    content += delta['content']
                        except:
                            continue

                return {
                    'success': True,
                    'time': time.time() - start_time,
                    'answer': content.strip()
                }

            return {'success': False, 'error': f'HTTP {response.status_code}'}

        except Exception as e:
            return {'success': False, 'error': str(e)[:30]}

    def test_non_stream(self, model):
        """测试非流式响应"""
        try:
            start_time = time.time()
            response = requests.post(
                f"{self.api_base}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.get_api_key()}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "1+1=?"}],
                    "max_tokens": 10,
                    "temperature": 0,
                    "stream": False
                },
                timeout=6,
                verify=False
            )

            if response.status_code == 200:
                data = response.json()
                if 'choices' in data and data['choices']:
                    answer = data['choices'][0]['message']['content'].strip()
                    return {
                        'success': True,
                        'time': time.time() - start_time,
                        'answer': answer
                    }

            return {'success': False, 'error': f'HTTP {response.status_code}'}

        except Exception as e:
            return {'success': False, 'error': str(e)[:30]}

    def run_fast_test(self, models, max_workers=8):
        """运行快速并发测试"""
        print(f"🚀 快速并发测试 {len(models)} 个模型")
        print(f"⚡ 线程数: {max_workers}")
        print(f"🔧 API: {self.api_base}")
        print("="*70)

        start_time = time.time()

        # 准备任务
        tasks = [(model, i+1, len(models)) for i, model in enumerate(models)]

        # 并发执行
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self.quick_test_model, task) for task in tasks]

            for future in as_completed(futures):
                result = future.result()

                if result['type'] == 'stream':
                    self.stream_models.append(result)
                elif result['type'] == 'non_stream':
                    self.non_stream_models.append(result)
                else:
                    self.failed_models.append(result)

        total_time = time.time() - start_time

        # 生成报告
        self.generate_fast_report(total_time)

        return {
            'stream_count': len(self.stream_models),
            'non_stream_count': len(self.non_stream_models),
            'failed_count': len(self.failed_models),
            'total_time': total_time
        }

    def generate_fast_report(self, total_time):
        """生成快速报告"""
        print(f"\n{'='*70}")
        print("📊 快速测试报告")
        print(f"{'='*70}")

        total = len(self.stream_models) + len(self.non_stream_models) + len(self.failed_models)
        success_count = len(self.stream_models) + len(self.non_stream_models)

        print(f"📋 测试结果:")
        print(f"  • 总模型数: {total}")
        print(f"  • 支持流式: {len(self.stream_models)} 个")
        print(f"  • 仅非流式: {len(self.non_stream_models)} 个")
        print(f"  • 完全失败: {len(self.failed_models)} 个")
        print(f"  • 成功率: {success_count/total*100:.1f}%")
        print(f"  • 总耗时: {total_time:.1f}秒")

        # 显示最快的流式模型
        if self.stream_models:
            fastest_stream = min(self.stream_models, key=lambda x: x['result']['time'])
            print(f"\n🏆 最快流式模型:")
            print(f"  {fastest_stream['model']}")
            print(f"  响应时间: {fastest_stream['result']['time']:.2f}s")
            print(f"  回答: {fastest_stream['result']['answer']}")

        # 显示最快的非流式模型
        if self.non_stream_models:
            fastest_non_stream = min(self.non_stream_models, key=lambda x: x['result']['time'])
            print(f"\n🥈 最快非流式模型:")
            print(f"  {fastest_non_stream['model']}")
            print(f"  响应时间: {fastest_non_stream['result']['time']:.2f}s")
            print(f"  回答: {fastest_non_stream['result']['answer']}")

        # 推荐配置
        all_working = self.stream_models + self.non_stream_models
        if all_working:
            best_model = min(all_working, key=lambda x: x['result']['time'])
            print(f"\n🔧 推荐配置:")
            print(f'"model": "{best_model["model"]}"')

def main():
    # 读取配置
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 使用第一个激活的第三方API配置
    third_party_apis = config.get('third_party_apis', [])
    if not third_party_apis:
        print("❌ 未找到第三方API配置")
        return

    primary_api = None
    for api in third_party_apis:
        if api.get('is_active', True):
            primary_api = api
            break

    if not primary_api:
        primary_api = third_party_apis[0]

    api_base = primary_api['api_base']
    api_keys = primary_api['api_keys']
    all_models = primary_api['models']  # 直接使用配置中的模型列表

    print(f"🔧 使用代理: {primary_api['name']}")
    print(f"🌐 API地址: {api_base}")
    print(f"🔑 密钥数量: {len(api_keys)}")
    print(f"🤖 模型数量: {len(all_models)}")
    print()

    # 创建快速测试器
    tester = FastModelTester(api_base, api_keys)

    # 运行快速测试
    summary = tester.run_fast_test(all_models, max_workers=10)

    # 保存结果
    results = {
        'summary': summary,
        'stream_models': [{'model': m['model'], 'time': m['result']['time'], 'answer': m['result']['answer']} for m in tester.stream_models],
        'non_stream_models': [{'model': m['model'], 'time': m['result']['time'], 'answer': m['result']['answer']} for m in tester.non_stream_models],
        'failed_models': [{'model': m['model'], 'error': m['result']['error']} for m in tester.failed_models],
        'test_time': time.strftime('%Y-%m-%d %H:%M:%S')
    }

    with open('fast_test_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n💾 结果已保存到 fast_test_results.json")

if __name__ == "__main__":
    main()
