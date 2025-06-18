#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API密钥切换器（简化版本）
不再需要session获取token功能，直接使用配置文件中的API密钥
"""

import json
import logging
import time
import threading
import requests
# from datetime import datetime  # 不再需要

logger = logging.getLogger(__name__)

# 全局变量
key_switch_lock = threading.Lock()
last_switch_time = 0
base_cooldown = 30  # 基础冷却时间（秒）
max_cooldown = 300  # 最大冷却时间（秒）
cooldown_factor = 1.0  # 冷却系数

# 系统状态
system_status = {
    "version": "1.0.0",
    "model": "unknown",
    "quota_per_unit": 1000,
    "last_updated": 0
}

class KeySwitcher:
    """API密钥切换器（简化版本）"""

    def __init__(self, config_file='config.json', add_prefix=True):
        self.config_file = config_file
        self.add_prefix = add_prefix
        self.current_key = None
        self.used_keys = set()
        self.key_usage_history = {}

        # 加载当前配置
        config = self.load_config()
        if config:
            self.current_key = config.get('third_party_apis', {}).get('api_key', '')

    def load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return None

    def save_config(self, config):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            logger.info("配置文件保存成功")
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False

    def get_available_models(self):
        """从第三方API获取可用模型列表"""
        try:
            # 从配置中获取API信息
            config = self.load_config()
            if not config:
                return []

            api_base = config.get('third_party_apis', {}).get('api_base', '')
            api_key = config.get('third_party_apis', {}).get('api_key', '')

            if not api_base or not api_key:
                logger.warning("API配置不完整，无法获取模型列表")
                return []

            # 构建模型列表API URL
            models_url = f"{api_base.rstrip('/')}/v1/models"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            response = requests.get(models_url, headers=headers, timeout=10, verify=False)
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    models = [model.get("id", "") for model in data["data"] if model.get("id")]
                    logger.info(f"从API获取到 {len(models)} 个可用模型")
                    return models
            else:
                logger.warning(f"获取模型列表失败: HTTP {response.status_code}")
        except Exception as e:
            logger.warning(f"获取模型列表异常: {e}")

        # 如果API调用失败，从配置文件获取
        try:
            config = self.load_config()
            models = config.get('third_party_apis', {}).get('models', [])
            logger.info(f"从配置文件获取到 {len(models)} 个模型")
            return models
        except:
            logger.warning("无法从配置文件获取模型列表")
            return []

    def get_tokens(self):
        """获取可用的token列表（已禁用）"""
        # 不再需要获取token列表功能
        logger.info("Token获取功能已禁用")
        return []

    def switch_key(self):
        """执行密钥切换（简化版本）"""
        global last_switch_time, cooldown_factor

        # 计算实际冷却时间
        actual_cooldown = min(base_cooldown * cooldown_factor, max_cooldown)

        # 防止频繁切换
        current_time = time.time()
        if current_time - last_switch_time < actual_cooldown:
            logger.info(f"冷却中，跳过密钥切换 (上次切换: {current_time - last_switch_time:.2f}秒前)")
            return False

        # 获取线程锁
        if not key_switch_lock.acquire(blocking=False):
            logger.info("另一个线程正在切换密钥，跳过")
            return False

        try:
            logger.info("开始切换API密钥...")
            # 简化版本：不切换密钥，只记录日志
            logger.info("密钥切换功能已简化，使用配置文件中的固定密钥")
            last_switch_time = time.time()
            return True
        finally:
            # 释放锁
            key_switch_lock.release()

    def report_key_success(self):
        """报告当前密钥使用成功"""
        if self.current_key:
            logger.debug("当前密钥使用成功")

    def report_key_failure(self, error_type=None):
        """报告当前密钥使用失败"""
        if self.current_key:
            logger.warning(f"当前密钥使用失败: {error_type}")

# 全局单例
_switcher = None

def get_switcher(config_file='config.json', add_prefix=True):
    """获取KeySwitcher单例"""
    global _switcher
    if _switcher is None:
        _switcher = KeySwitcher(config_file, add_prefix)
    return _switcher

def should_switch_key(status_code, error_message=None):
    """判断是否需要切换密钥"""
    # 简化版本：不切换密钥
    return False

def get_error_type(status_code, error_message=None):
    """从错误响应中识别错误类型"""
    if status_code >= 500:
        return "server_error"
    elif status_code == 401 or status_code == 403:
        return "auth_error"
    elif status_code == 429:
        return "rate_limit"
    elif status_code == 408:
        return "timeout"
    return "unknown"

def switch_key_if_needed(status_code, error_message=None):
    """如果需要，切换密钥"""
    # 简化版本：不切换密钥
    return False

def report_key_success():
    """报告当前密钥使用成功"""
    switcher = get_switcher()
    switcher.report_key_success()

def get_failure_stats():
    """获取所有密钥的失败统计信息"""
    return {}

def clear_token_cache():
    """清除Token详情缓存"""
    try:
        # 清除代理池相关的缓存
        cleared_count = 0

        # 这里可以添加具体的缓存清除逻辑
        # 例如：清除Redis缓存、内存缓存等

        logger.info(f"Token缓存清除完成，清除了 {cleared_count} 条记录")
        return cleared_count
    except Exception as e:
        logger.error(f"Token缓存清除失败: {e}")
        return 0

def get_system_status():
    """获取系统状态信息"""
    return system_status

if __name__ == "__main__":
    # 测试代码
    switcher = get_switcher()
    success = switcher.switch_key()
    print(f"密钥切换结果: {'成功' if success else '失败'}")
