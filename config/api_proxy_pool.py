#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第三方API代理池管理器
支持多个代理服务的负载均衡和故障转移
"""

import json
import random
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from config.config import Config

logger = logging.getLogger(__name__)

@dataclass
class ApiProxy:
    """API代理配置"""
    name: str
    api_base: str
    api_keys: List[str]
    model: str
    models: List[str]
    is_active: bool = True
    priority: int = 1

    @property
    def current_api_key(self) -> Optional[str]:
        """获取当前可用的API密钥"""
        return self.api_keys[0] if self.api_keys else None

    def get_random_api_key(self) -> Optional[str]:
        """随机获取一个API密钥"""
        return random.choice(self.api_keys) if self.api_keys else None

class ApiProxyPool:
    """第三方API代理池管理器"""

    def __init__(self):
        self.proxies: List[ApiProxy] = []
        self.load_proxies()

    def load_proxies(self):
        """从配置文件加载代理列表"""
        try:
            self.proxies = []

            # 直接从config.json文件读取，支持热重载
            try:
                with open('config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                proxy_configs = config.get('third_party_apis', [])
            except Exception as e:
                logger.warning(f"无法读取config.json，使用Config类配置: {e}")
                proxy_configs = Config.THIRD_PARTY_APIS

            for proxy_config in proxy_configs:
                proxy = ApiProxy(
                    name=proxy_config.get('name', 'Unknown API'),
                    api_base=proxy_config.get('api_base', ''),
                    api_keys=proxy_config.get('api_keys', []),
                    model=proxy_config.get('model', ''),
                    models=proxy_config.get('models', []),
                    is_active=proxy_config.get('is_active', True),
                    priority=proxy_config.get('priority', 1)
                )
                self.proxies.append(proxy)

            # 按优先级排序
            self.proxies.sort(key=lambda x: x.priority)
            logger.info(f"加载了 {len(self.proxies)} 个API代理")

        except Exception as e:
            logger.error(f"加载API代理配置失败: {e}")
            self.proxies = []

    def get_active_proxies(self) -> List[ApiProxy]:
        """获取所有激活的代理"""
        return [proxy for proxy in self.proxies if proxy.is_active]

    def get_primary_proxy(self) -> Optional[ApiProxy]:
        """获取主要代理（优先级最高的激活代理）"""
        active_proxies = self.get_active_proxies()
        return active_proxies[0] if active_proxies else None

    def get_proxy_by_name(self, name: str) -> Optional[ApiProxy]:
        """根据名称获取代理"""
        for proxy in self.proxies:
            if proxy.name == name:
                return proxy
        return None

    def get_next_proxy(self, exclude_names: List[str] = None) -> Optional[ApiProxy]:
        """获取下一个可用的代理（用于故障转移）"""
        exclude_names = exclude_names or []
        active_proxies = self.get_active_proxies()

        for proxy in active_proxies:
            if proxy.name not in exclude_names:
                return proxy

        return None

    def get_random_proxy(self) -> Optional[ApiProxy]:
        """随机获取一个激活的代理（用于负载均衡）"""
        active_proxies = self.get_active_proxies()
        return random.choice(active_proxies) if active_proxies else None

    def get_proxy_for_model(self, model: str) -> Optional[ApiProxy]:
        """根据模型名称获取支持该模型的代理"""
        active_proxies = self.get_active_proxies()

        for proxy in active_proxies:
            if model in proxy.models:
                return proxy

        # 如果没有找到支持该模型的代理，返回主要代理
        return self.get_primary_proxy()

    def get_all_models(self) -> List[str]:
        """获取所有代理支持的模型列表"""
        all_models = set()
        for proxy in self.get_active_proxies():
            all_models.update(proxy.models)
        return sorted(list(all_models))

    def get_proxy_stats(self) -> Dict[str, Any]:
        """获取代理池统计信息"""
        active_proxies = self.get_active_proxies()
        total_keys = sum(len(proxy.api_keys) for proxy in active_proxies)
        total_models = len(self.get_all_models())

        return {
            'total_proxies': len(self.proxies),
            'active_proxies': len(active_proxies),
            'total_api_keys': total_keys,
            'total_models': total_models,
            'proxies': [
                {
                    'name': proxy.name,
                    'api_base': proxy.api_base,
                    'api_keys_count': len(proxy.api_keys),
                    'models_count': len(proxy.models),
                    'is_active': proxy.is_active,
                    'priority': proxy.priority
                }
                for proxy in self.proxies
            ]
        }

    def reload_config(self):
        """重新加载配置"""
        logger.info("重新加载API代理池配置")
        self.load_proxies()

# 全局代理池实例
api_proxy_pool = ApiProxyPool()

def get_api_proxy_pool(reload: bool = False) -> ApiProxyPool:
    """获取全局代理池实例"""
    global api_proxy_pool
    if reload:
        api_proxy_pool.reload_config()
    return api_proxy_pool
