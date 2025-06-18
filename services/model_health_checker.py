#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型健康检查服务
定期检查第三方API模型的可用性和API密钥池的健康状态
"""

import requests
import json
import time
import logging
import urllib3
from datetime import datetime, timedelta
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import os

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ModelHealthChecker:
    def __init__(self, config_path: str = 'config.json'):
        self.config_path = config_path
        self.config = self.load_config()

        # 使用第一个激活的第三方API配置
        third_party_apis = self.config.get('third_party_apis', [])
        if not third_party_apis:
            raise ValueError("未找到第三方API配置")

        primary_api = None
        for api in third_party_apis:
            if api.get('is_active', True):
                primary_api = api
                break

        if not primary_api:
            primary_api = third_party_apis[0]

        self.api_base = primary_api['api_base']
        self.api_keys = primary_api['api_keys']
        self.models = primary_api['models']

        # 设置日志
        self.setup_logging()

        # 线程锁
        self.key_lock = threading.Lock()
        self.key_index = 0

        # 健康状态
        self.healthy_models = []
        self.unhealthy_models = []
        self.healthy_keys = []
        self.unhealthy_keys = []

    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            raise Exception(f"无法加载配置文件: {e}")

    def setup_logging(self):
        """设置日志"""
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'{log_dir}/model_health.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('ModelHealthChecker')

    def get_next_key(self) -> str:
        """线程安全地获取下一个API密钥"""
        with self.key_lock:
            key = self.api_keys[self.key_index]
            self.key_index = (self.key_index + 1) % len(self.api_keys)
            return key

    def test_api_key(self, api_key: str) -> Dict[str, Any]:
        """测试单个API密钥"""
        try:
            response = requests.get(
                f"{self.api_base}/v1/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                timeout=10,
                verify=False
            )

            if response.status_code == 200:
                return {"success": True, "key": api_key[:20] + "..."}
            else:
                return {"success": False, "key": api_key[:20] + "...", "error": f"HTTP {response.status_code}"}

        except Exception as e:
            return {"success": False, "key": api_key[:20] + "...", "error": str(e)[:50]}

    def test_model(self, model: str) -> Dict[str, Any]:
        """测试单个模型"""
        api_key = self.get_next_key()

        try:
            response = requests.post(
                f"{self.api_base}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 5,
                    "temperature": 0,
                    "stream": True
                },
                stream=True,
                timeout=8,
                verify=False
            )

            if response.status_code == 200:
                # 简单验证流式响应
                for line in response.iter_lines():
                    if line and b'data:' in line:
                        return {"success": True, "model": model}
                return {"success": True, "model": model}
            else:
                return {"success": False, "model": model, "error": f"HTTP {response.status_code}"}

        except Exception as e:
            return {"success": False, "model": model, "error": str(e)[:50]}

    def check_api_keys_health(self) -> Dict[str, Any]:
        """检查API密钥池健康状态"""
        self.logger.info("开始检查API密钥池健康状态...")

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self.test_api_key, key) for key in self.api_keys]

            for future in as_completed(futures):
                result = future.result()
                if result['success']:
                    self.healthy_keys.append(result)
                else:
                    self.unhealthy_keys.append(result)

        health_rate = len(self.healthy_keys) / len(self.api_keys) * 100

        self.logger.info(f"API密钥健康检查完成: {len(self.healthy_keys)}/{len(self.api_keys)} ({health_rate:.1f}%)")

        return {
            "total_keys": len(self.api_keys),
            "healthy_keys": len(self.healthy_keys),
            "unhealthy_keys": len(self.unhealthy_keys),
            "health_rate": health_rate
        }

    def check_models_health(self, sample_size: int = 10) -> Dict[str, Any]:
        """检查模型健康状态（采样测试）"""
        # 采样测试，避免测试所有模型
        test_models = self.models[:sample_size] if len(self.models) > sample_size else self.models

        self.logger.info(f"开始检查模型健康状态（采样 {len(test_models)} 个模型）...")

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(self.test_model, model) for model in test_models]

            for future in as_completed(futures):
                result = future.result()
                if result['success']:
                    self.healthy_models.append(result)
                else:
                    self.unhealthy_models.append(result)

        health_rate = len(self.healthy_models) / len(test_models) * 100

        self.logger.info(f"模型健康检查完成: {len(self.healthy_models)}/{len(test_models)} ({health_rate:.1f}%)")

        return {
            "tested_models": len(test_models),
            "healthy_models": len(self.healthy_models),
            "unhealthy_models": len(self.unhealthy_models),
            "health_rate": health_rate
        }

    def update_config_if_needed(self) -> bool:
        """如果需要，更新配置文件（移除不健康的模型）"""
        if not self.unhealthy_models:
            return False

        unhealthy_model_names = [m['model'] for m in self.unhealthy_models]

        # 找到第一个激活的第三方API配置
        third_party_apis = self.config.get('third_party_apis', [])
        primary_api = None
        for api in third_party_apis:
            if api.get('is_active', True):
                primary_api = api
                break

        if not primary_api and third_party_apis:
            primary_api = third_party_apis[0]

        if not primary_api:
            self.logger.error("未找到第三方API配置")
            return False

        original_count = len(primary_api['models'])

        # 移除不健康的模型
        primary_api['models'] = [
            model for model in primary_api['models']
            if model not in unhealthy_model_names
        ]

        # 如果当前默认模型不健康，切换到健康的模型
        current_model = primary_api['model']
        if current_model in unhealthy_model_names and self.healthy_models:
            new_model = self.healthy_models[0]['model']
            primary_api['model'] = new_model
            self.logger.warning(f"默认模型已从 {current_model} 切换到 {new_model}")

        # 保存更新的配置
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)

            removed_count = original_count - len(primary_api['models'])
            self.logger.info(f"配置已更新，移除了 {removed_count} 个不健康的模型")
            return True

        except Exception as e:
            self.logger.error(f"更新配置文件失败: {e}")
            return False

    def generate_health_report(self) -> Dict[str, Any]:
        """生成健康检查报告"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "api_keys": {
                "total": len(self.api_keys),
                "healthy": len(self.healthy_keys),
                "unhealthy": len(self.unhealthy_keys),
                "health_rate": len(self.healthy_keys) / len(self.api_keys) * 100
            },
            "models": {
                "tested": len(self.healthy_models) + len(self.unhealthy_models),
                "healthy": len(self.healthy_models),
                "unhealthy": len(self.unhealthy_models),
                "health_rate": len(self.healthy_models) / (len(self.healthy_models) + len(self.unhealthy_models)) * 100 if (len(self.healthy_models) + len(self.unhealthy_models)) > 0 else 0
            },
            "healthy_models": [m['model'] for m in self.healthy_models],
            "unhealthy_models": [{"model": m['model'], "error": m.get('error', 'Unknown')} for m in self.unhealthy_models],
            "unhealthy_keys": [{"key": k['key'], "error": k.get('error', 'Unknown')} for k in self.unhealthy_keys]
        }

        # 保存报告
        report_file = f"logs/health_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            self.logger.info(f"健康检查报告已保存到 {report_file}")
        except Exception as e:
            self.logger.error(f"保存健康检查报告失败: {e}")

        return report

    def run_health_check(self, update_config: bool = True) -> Dict[str, Any]:
        """运行完整的健康检查"""
        self.logger.info("开始运行模型健康检查...")
        start_time = time.time()

        # 重置状态
        self.healthy_models = []
        self.unhealthy_models = []
        self.healthy_keys = []
        self.unhealthy_keys = []

        # 检查API密钥
        key_health = self.check_api_keys_health()

        # 检查模型（如果有健康的密钥）
        model_health = {}
        if self.healthy_keys:
            model_health = self.check_models_health()
        else:
            self.logger.error("没有健康的API密钥，跳过模型检查")

        # 更新配置（如果需要）
        config_updated = False
        if update_config and self.unhealthy_models:
            config_updated = self.update_config_if_needed()

        # 生成报告
        report = self.generate_health_report()
        report['config_updated'] = config_updated
        report['duration'] = time.time() - start_time

        self.logger.info(f"健康检查完成，耗时 {report['duration']:.1f} 秒")

        return report

def main():
    """主函数"""
    checker = ModelHealthChecker()
    report = checker.run_health_check()

    print(f"🏥 模型健康检查报告")
    print(f"{'='*50}")
    print(f"🔑 API密钥: {report['api_keys']['healthy']}/{report['api_keys']['total']} 健康")
    print(f"🤖 模型: {report['models']['healthy']}/{report['models']['tested']} 健康")
    print(f"⏱️ 耗时: {report['duration']:.1f} 秒")

    if report['config_updated']:
        print(f"🔧 配置已自动更新")

if __name__ == "__main__":
    main()
