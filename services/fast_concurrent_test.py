#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速并发模型测试器
用于批量测试第三方API代理池中的模型
"""

import asyncio
import aiohttp
import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import ssl

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FastModelTester:
    """快速模型测试器"""
    
    def __init__(self, api_base: str, api_keys: List[str]):
        """
        初始化测试器
        
        Args:
            api_base: API基础URL
            api_keys: API密钥列表
        """
        self.api_base = api_base.rstrip('/')
        self.api_keys = api_keys
        self.test_message = "Hello"
        self.timeout = 10
        
    def test_model_sync(self, model: str, api_key: str) -> Dict[str, Any]:
        """
        同步测试单个模型
        
        Args:
            model: 模型名称
            api_key: API密钥
            
        Returns:
            测试结果字典
        """
        import requests
        
        # 构建API URL
        if '/chat/completions' in self.api_base:
            url = self.api_base
        elif self.api_base.endswith('/v1'):
            url = f"{self.api_base}/chat/completions"
        else:
            url = f"{self.api_base}/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 测试非流式响应
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": self.test_message}],
            "max_tokens": 10,
            "temperature": 0.1,
            "stream": False
        }
        
        result = {
            "model": model,
            "api_key": api_key[:20] + "...",
            "success": False,
            "stream_support": False,
            "non_stream_support": False,
            "response_time": 0,
            "error": None
        }
        
        try:
            start_time = time.time()
            
            # 测试非流式
            response = requests.post(
                url, 
                headers=headers, 
                json=payload, 
                timeout=self.timeout,
                verify=False
            )
            
            response_time = time.time() - start_time
            result["response_time"] = round(response_time, 2)
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    result["non_stream_support"] = True
                    result["success"] = True
                    
                    # 测试流式响应
                    try:
                        stream_payload = payload.copy()
                        stream_payload["stream"] = True
                        
                        stream_response = requests.post(
                            url,
                            headers=headers,
                            json=stream_payload,
                            timeout=self.timeout,
                            verify=False,
                            stream=True
                        )
                        
                        if stream_response.status_code == 200:
                            # 检查是否返回流式数据
                            for line in stream_response.iter_lines():
                                if line:
                                    line_str = line.decode('utf-8')
                                    if line_str.startswith('data: '):
                                        result["stream_support"] = True
                                        break
                                    
                    except Exception as stream_error:
                        logger.debug(f"流式测试失败 {model}: {stream_error}")
                        
            else:
                result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
                
        except Exception as e:
            result["error"] = str(e)
            
        return result
    
    def run_fast_test(self, models: List[str], max_workers: int = 5) -> Dict[str, Any]:
        """
        运行快速并发测试
        
        Args:
            models: 要测试的模型列表
            max_workers: 最大并发数
            
        Returns:
            测试摘要
        """
        logger.info(f"开始测试 {len(models)} 个模型，并发数: {max_workers}")
        
        results = []
        successful_models = []
        failed_models = []
        stream_models = []
        non_stream_models = []
        
        # 使用线程池进行并发测试
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 为每个模型创建测试任务
            future_to_model = {}
            
            for model in models:
                # 轮询使用API密钥
                api_key = self.api_keys[len(future_to_model) % len(self.api_keys)]
                future = executor.submit(self.test_model_sync, model, api_key)
                future_to_model[future] = model
            
            # 收集结果
            for future in as_completed(future_to_model):
                model = future_to_model[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result["success"]:
                        successful_models.append(result)
                        if result["stream_support"]:
                            stream_models.append(result)
                        if result["non_stream_support"]:
                            non_stream_models.append(result)
                    else:
                        failed_models.append(result)
                        
                    # 实时输出结果
                    status = "✅" if result["success"] else "❌"
                    stream_status = "🔄" if result["stream_support"] else "📝"
                    logger.info(f"{status} {stream_status} {model} ({result['response_time']}s)")
                    
                except Exception as e:
                    logger.error(f"测试 {model} 时发生异常: {e}")
                    failed_models.append({
                        "model": model,
                        "success": False,
                        "error": str(e)
                    })
        
        # 生成摘要
        summary = {
            "total_models": len(models),
            "successful_count": len(successful_models),
            "failed_count": len(failed_models),
            "stream_count": len(stream_models),
            "non_stream_count": len(non_stream_models),
            "success_rate": round(len(successful_models) / len(models) * 100, 1) if models else 0,
            "successful_models": [r["model"] for r in successful_models],
            "failed_models": [r["model"] for r in failed_models],
            "stream_models": [r["model"] for r in stream_models],
            "results": results
        }
        
        # 输出摘要
        logger.info(f"\n📊 测试完成摘要:")
        logger.info(f"  总模型数: {summary['total_models']}")
        logger.info(f"  成功: {summary['successful_count']} ({summary['success_rate']}%)")
        logger.info(f"  失败: {summary['failed_count']}")
        logger.info(f"  支持流式: {summary['stream_count']}")
        logger.info(f"  支持非流式: {summary['non_stream_count']}")
        
        return summary

def main():
    """主函数，用于独立运行测试"""
    # 读取配置
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"无法读取配置文件: {e}")
        return
    
    # 使用第一个激活的第三方API配置
    third_party_apis = config.get('third_party_apis', [])
    if not third_party_apis:
        logger.error("未找到第三方API配置")
        return
    
    primary_api = None
    for api in third_party_apis:
        if api.get('is_active', True):
            primary_api = api
            break
    
    if not primary_api:
        primary_api = third_party_apis[0]
    
    # 创建测试器
    tester = FastModelTester(primary_api['api_base'], primary_api['api_keys'])
    
    # 运行测试
    summary = tester.run_fast_test(primary_api['models'], max_workers=3)
    
    # 保存结果
    with open('test_results.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    logger.info("测试结果已保存到 test_results.json")

if __name__ == "__main__":
    main()
