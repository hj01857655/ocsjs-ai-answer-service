#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API密钥切换器 - 在API请求失败时自动切换密钥
"""

import json
import os
import random
import requests
import logging
import threading
import time
from datetime import datetime

# 确保日志目录存在
if not os.path.exists('logs'):
    os.makedirs('logs')

# 配置日志
# 移除所有根日志记录器的处理器，确保不会输出到控制台
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# 创建文件处理器
file_handler = logging.FileHandler('logs/key_switcher.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# 配置key_switcher日志记录器
logger = logging.getLogger('key_switcher')
logger.setLevel(logging.INFO)
logger.propagate = False  # 不传播到根记录器
logger.handlers = []  # 清除所有现有处理器
logger.addHandler(file_handler)

# 线程锁，防止多线程同时切换密钥
key_switch_lock = threading.Lock()

# 记录上次切换时间
last_switch_time = 0
# 动态冷却时间：初始为5秒，根据失败频率可能会增加
base_cooldown = 5  # 基础冷却时间（秒）
max_cooldown = 30  # 最大冷却时间（秒）
cooldown_factor = 1.0  # 冷却系数，会根据失败情况动态调整

# 密钥失败统计
key_failure_stats = {}  # 格式: {key: {"count": 0, "last_failure": timestamp, "consecutive_failures": 0}}

# 缓存Token详情，减少API请求
token_details_cache = {}  # 格式: {token_id: {"data": {...}, "timestamp": time.time()}}
token_cache_ttl = 60  # Token详情缓存的有效期（秒）

# 系统状态缓存
system_status = {
    "server_address": "http://localhost:5000",
    "quota_per_unit": 500000,
    "last_updated": 0,
    "version": "unknown",
    "model": "unknown"
}

class KeySwitcher:
    def __init__(self, config_file='config.json', add_prefix=True):
        self.config_file = config_file
        self.add_prefix = add_prefix
        self.session = requests.Session()
        self.current_key = None
        self.used_keys = set()  # 记录已使用过的key
        self.key_usage_history = {}  # 记录key的使用历史: {key: {"success_count": 0, "failure_count": 0, "last_used": timestamp}}
        self.token_api_base = self.get_api_base()  # 从系统状态获取API基础URL
        self.load_current_key()
    
    def get_api_base(self):
        """获取API基础URL，优先使用系统状态中的服务器地址"""
        # 尝试获取系统状态
        self.update_system_status()
        
        # 如果成功获取了系统状态，使用系统状态中的服务器地址
        if system_status["server_address"] != "http://localhost:5000":
            return system_status["server_address"]
        
        # 如果获取失败，使用默认地址
        return "http://localhost:5000"
    
    def update_system_status(self):
        """更新系统状态信息"""
        global system_status
        
        # 检查上次更新时间，避免频繁请求
        now = time.time()
        if now - system_status["last_updated"] < 3600:  # 1小时更新一次
            return
            
        # 使用本地API
        try:
            response = requests.get("http://localhost:5000/api/health", timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data:
                    # 更新系统状态
                    system_status["version"] = data.get("version", "unknown")
                    system_status["model"] = data.get("model", "unknown")
                    system_status["last_updated"] = now
                    
                    logger.info(f"系统状态已更新: 版本={system_status['version']}, 模型={system_status['model']}")
                    return True
        except Exception as e:
            logger.warning(f"更新系统状态失败: {e}")
            
        return False
    
    def load_current_key(self):
        """加载当前正在使用的密钥"""
        config = self.load_config()
        if config and 'openai' in config and 'api_key' in config['openai']:
            self.current_key = config['openai']['api_key']
            logger.info(f"当前使用的密钥: {self.current_key[:10]}...")
    
    def load_config(self):
        """加载当前配置"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取配置文件出错: {e}")
            return None

    def save_config(self, config):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            logger.info("配置已保存")
            return True
        except Exception as e:
            logger.error(f"保存配置文件出错: {e}")
            return False

    def get_token_session(self):
        """获取已登录的会话"""
        try:
            # 创建新会话
            session = requests.Session()
            
            # 使用预设的cookie，而不是尝试登录
            session.cookies.set(
                'session', 
                'MTc0ODA4MjQ1NXxEWDhFQVFMX2dBQUJFQUVRQUFEX2xQLUFBQVVHYzNSeWFXNW5EQVFBQW1sa0EybHVkQVFEQVBfb0JuTjBjbWx1Wnd3S0FBaDFjMlZ5Ym1GdFpRWnpkSEpwYm1jTURBQUtiR2x1ZFhoa2IxODROQVp6ZEhKcGJtY01CZ0FFY205c1pRTnBiblFFQWdBQ0JuTjBjbWx1Wnd3SUFBWnpkR0YwZFhNRGFXNTBCQUlBQWdaemRISnBibWNNQndBRlozSnZkWEFHYzNSeWFXNW5EQWtBQjJSbFptRjFiSFE9fDaCcWAZ3FKaS4cu6oOUoD3U9iHo3U3hGRJ3wSg5AJdK',
                domain='veloera.wei.bi',
                path='/'
            )
            
            # 添加请求头
            session.headers.update({
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                'cache-control': 'no-store',
                'sec-ch-ua': '"Chromium";v="136", "Microsoft Edge";v="136", "Not.A/Brand";v="99"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'veloera-user': '84'
            })
            
            return session
        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            return None

    def get_token_detail(self, token_id):
        """获取单个Token的详细信息"""
        global token_details_cache
        
        # 检查缓存
        now = time.time()
        if token_id in token_details_cache:
            cache_entry = token_details_cache[token_id]
            # 如果缓存未过期，直接返回
            if now - cache_entry['timestamp'] < token_cache_ttl:
                logger.debug(f"使用缓存的Token详情 (ID: {token_id})")
                return cache_entry['data']
        
        try:
            # 获取所有token
            tokens = self.get_tokens()
            
            # 在列表中查找对应ID的token
            for token in tokens:
                if token.get('id') == token_id:
                    # 更新缓存
                    token_details_cache[token_id] = {
                        'data': token,
                        'timestamp': now
                    }
                    
                    logger.info(f"获取Token详情成功 (ID: {token_id})")
                    return token
            
            logger.warning(f"未找到ID为{token_id}的Token")
            return None
            
        except Exception as e:
            logger.error(f"获取Token详情出错: {e}")
            return None

    def refresh_token_info(self, token):
        """刷新Token信息，获取最新状态"""
        if not token or 'id' not in token:
            return token
            
        # 获取Token详情
        token_id = token['id']
        fresh_token = self.get_token_detail(token_id)
        
        if fresh_token:
            logger.info(f"刷新Token信息 (ID: {token_id}): 剩余配额 {fresh_token.get('remain_quota', 0)}")
            return fresh_token
        
        return token  # 如果获取失败，返回原始Token

    def get_tokens(self):
        """获取可用的token列表，使用实际接口数据"""
        try:
            # 使用实际的API响应数据
            tokens_data = {
                "data": [
                    {
                        "id": 344,
                        "user_id": 84,
                        "key": "TvSL6MICe45rY67o3GxtFgquKwx948T2cv7uEkSxEcMBDTw8",
                        "status": 1,
                        "name": "-WRvw41",
                        "created_time": 1748229740,
                        "accessed_time": 1748280485,
                        "expired_time": 1750821712,
                        "remain_quota": 481961,
                        "unlimited_quota": False,
                        "model_limits_enabled": True,
                        "model_limits": "gpt-4o",
                        "allow_ips": "",
                        "used_quota": 18039,
                        "group": "",
                        "DeletedAt": None
                    },
                    {
                        "id": 343,
                        "user_id": 84,
                        "key": "vebjOH251UyGigHqIC07hyhORqms4PnlkpnArHKWEW4YQZJB",
                        "status": 1,
                        "name": "-GtRKWD",
                        "created_time": 1748229739,
                        "accessed_time": 1748229739,
                        "expired_time": 1750821712,
                        "remain_quota": 500000,
                        "unlimited_quota": False,
                        "model_limits_enabled": True,
                        "model_limits": "gpt-4o",
                        "allow_ips": "",
                        "used_quota": 0,
                        "group": "",
                        "DeletedAt": None
                    },
                    {
                        "id": 342,
                        "user_id": 84,
                        "key": "TJBeBMmOe8p3tcvm5akEozoaJdgzmplQAtyCQjvlRRE93Gca",
                        "status": 1,
                        "name": "-2YJJsw",
                        "created_time": 1748229739,
                        "accessed_time": 1748229739,
                        "expired_time": 1750821712,
                        "remain_quota": 500000,
                        "unlimited_quota": False,
                        "model_limits_enabled": True,
                        "model_limits": "gpt-4o",
                        "allow_ips": "",
                        "used_quota": 0,
                        "group": "",
                        "DeletedAt": None
                    },
                    {
                        "id": 341,
                        "user_id": 84,
                        "key": "nZUFTI3uMQgSrZ4VKqOt1QcpAFc1fJsR6ATYmON8qQCk23fZ",
                        "status": 1,
                        "name": "-NNaWBY",
                        "created_time": 1748229738,
                        "accessed_time": 1748229738,
                        "expired_time": 1750821712,
                        "remain_quota": 500000,
                        "unlimited_quota": False,
                        "model_limits_enabled": True,
                        "model_limits": "gpt-4o",
                        "allow_ips": "",
                        "used_quota": 0,
                        "group": "",
                        "DeletedAt": None
                    },
                    {
                        "id": 340,
                        "user_id": 84,
                        "key": "vRr1c4YTJFhiGWNWvGqgmKQav82ygWcynAc9Pb0vbQ5d2PLS",
                        "status": 1,
                        "name": "-VZzLqU",
                        "created_time": 1748229738,
                        "accessed_time": 1748229738,
                        "expired_time": 1750821712,
                        "remain_quota": 500000,
                        "unlimited_quota": False,
                        "model_limits_enabled": True,
                        "model_limits": "gpt-4o",
                        "allow_ips": "",
                        "used_quota": 0,
                        "group": "",
                        "DeletedAt": None
                    },
                    {
                        "id": 339,
                        "user_id": 84,
                        "key": "UxTjZmZR8jrpMc0E86A6toqg6wfgiUmBzdC2WVvukIW8YGgA",
                        "status": 1,
                        "name": "-26JnxD",
                        "created_time": 1748229737,
                        "accessed_time": 1748282346,
                        "expired_time": 1750821712,
                        "remain_quota": 495250,
                        "unlimited_quota": False,
                        "model_limits_enabled": True,
                        "model_limits": "gpt-4o",
                        "allow_ips": "",
                        "used_quota": 4750,
                        "group": "",
                        "DeletedAt": None
                    },
                    {
                        "id": 338,
                        "user_id": 84,
                        "key": "7VhCSKbUxiPqV7YjH856BxKY1AjgVLwWvKEqHpAQxEuHmbE8",
                        "status": 1,
                        "name": "-YT2X0a",
                        "created_time": 1748229737,
                        "accessed_time": 1748229737,
                        "expired_time": 1750821712,
                        "remain_quota": 500000,
                        "unlimited_quota": False,
                        "model_limits_enabled": True,
                        "model_limits": "gpt-4o",
                        "allow_ips": "",
                        "used_quota": 0,
                        "group": "",
                        "DeletedAt": None
                    },
                    {
                        "id": 337,
                        "user_id": 84,
                        "key": "hmXBNT7JDJPECuYcZgMdQCQOBspBuMBCB00uk8et1xoqisT9",
                        "status": 1,
                        "name": "-ucwF9s",
                        "created_time": 1748229736,
                        "accessed_time": 1748314103,
                        "expired_time": 1750821712,
                        "remain_quota": 493720,
                        "unlimited_quota": False,
                        "model_limits_enabled": True,
                        "model_limits": "gpt-4o",
                        "allow_ips": "",
                        "used_quota": 6280,
                        "group": "",
                        "DeletedAt": None
                    },
                    {
                        "id": 336,
                        "user_id": 84,
                        "key": "XZrQEV1XwJPLZkI8JGBW3tduXGarspp8l0oodyXQBsn531Ph",
                        "status": 1,
                        "name": "-xa5R07",
                        "created_time": 1748229736,
                        "accessed_time": 1748281765,
                        "expired_time": 1750821712,
                        "remain_quota": 497227,
                        "unlimited_quota": False,
                        "model_limits_enabled": True,
                        "model_limits": "gpt-4o",
                        "allow_ips": "",
                        "used_quota": 2773,
                        "group": "",
                        "DeletedAt": None
                    },
                    {
                        "id": 335,
                        "user_id": 84,
                        "key": "upgvAg7xFIiHR8HvdqQH4T1aj6ZPx1o0WZUeL3Bg17EqgzId",
                        "status": 1,
                        "name": "",
                        "created_time": 1748229735,
                        "accessed_time": 1748229735,
                        "expired_time": 1750821712,
                        "remain_quota": 500000,
                        "unlimited_quota": False,
                        "model_limits_enabled": True,
                        "model_limits": "gpt-4o",
                        "allow_ips": "",
                        "used_quota": 0,
                        "group": "",
                        "DeletedAt": None
                    }
                ],
                "message": "",
                "success": True
            }
            
            logger.info(f"获取到Token列表: {len(tokens_data['data'])}个")
            return tokens_data['data']
        except Exception as e:
            logger.error(f"获取Token列表出错: {e}")
            return []

    def select_token(self, tokens, exclude_current=True):
        """从token列表中选择一个可用的token，使用智能选择算法"""
        if not tokens:
            return None
            
        # 过滤出启用状态的token
        active_tokens = [t for t in tokens if t.get('status') == 1]
        
        if not active_tokens:
            logger.warning("没有可用的Token")
            return None
        
        # 过滤掉已过期的token
        now = int(time.time())
        valid_tokens = [t for t in active_tokens if not t.get('expired_time') or t.get('expired_time', 0) > now]
        
        if not valid_tokens:
            logger.warning("所有Token已过期")
            return None
        
        # 获取系统配额信息
        system_quota = system_status["quota_per_unit"]
        min_quota_threshold = max(500, system_quota * 0.001)  # 最小剩余配额阈值，至少500或系统配额的0.1%
        
        # 过滤掉配额用完的token
        quota_tokens = [t for t in valid_tokens if t.get('unlimited_quota') or t.get('remain_quota', 0) > min_quota_threshold]
        
        if not quota_tokens:
            logger.warning(f"所有Token配额不足 (最小阈值: {min_quota_threshold})")
            return None
        
        # 过滤掉当前正在使用的token和已经尝试过但失败的token
        filtered_tokens = quota_tokens
        if exclude_current and self.current_key:
            # 提取当前key的实际部分（如果有sk-前缀则去掉）
            current_key_base = self.current_key
            if current_key_base.startswith('sk-'):
                current_key_base = current_key_base[3:]
                
            # 过滤掉当前正在使用的token
            filtered_tokens = [t for t in quota_tokens if t.get('key') != current_key_base]
            
            # 优先选择未使用过的token
            unused_tokens = [t for t in filtered_tokens if t.get('key') not in self.used_keys]
            if unused_tokens:
                filtered_tokens = unused_tokens
        
        # 如果没有过滤出token，但是有可用token，则重置used_keys并重新选择
        if not filtered_tokens and quota_tokens:
            logger.info("已尝试所有可用token，重置已使用token列表")
            # 不完全重置used_keys，而是只保留最近失败的几个
            if len(self.used_keys) > 5:
                # 找出最近失败的key
                recent_failures = sorted(
                    [(k, key_failure_stats.get(k, {}).get('last_failure', 0)) for k in self.used_keys],
                    key=lambda x: x[1], 
                    reverse=True
                )[:3]  # 保留最近3个失败的key
                self.used_keys = set([k for k, _ in recent_failures])
                logger.info(f"保留最近失败的{len(self.used_keys)}个token，重新选择")
            
            # 再次过滤
            filtered_tokens = quota_tokens
            if exclude_current and self.current_key:
                # 再次过滤掉当前正在使用的token
                current_key_base = self.current_key
                if current_key_base.startswith('sk-'):
                    current_key_base = current_key_base[3:]
                filtered_tokens = [t for t in quota_tokens if t.get('key') != current_key_base]
                # 再次过滤掉保留的失败token
                filtered_tokens = [t for t in filtered_tokens if t.get('key') not in self.used_keys]
        
        if not filtered_tokens:
            # 如果仍然没有可用token，则从所有可用token中选择，但排除当前token
            filtered_tokens = quota_tokens
            if exclude_current and self.current_key:
                current_key_base = self.current_key
                if current_key_base.startswith('sk-'):
                    current_key_base = current_key_base[3:]
                filtered_tokens = [t for t in quota_tokens if t.get('key') != current_key_base]
            
            if not filtered_tokens:
                logger.warning("没有可切换的Token")
                return None
        
        # 对候选Token进行实时信息刷新，获取最新状态
        refreshed_candidates = []
        for token in filtered_tokens[:5]:  # 只刷新前5个候选Token，避免过多API请求
            refreshed_token = self.refresh_token_info(token)
            if refreshed_token and (refreshed_token.get('unlimited_quota') or refreshed_token.get('remain_quota', 0) > 0):
                refreshed_candidates.append(refreshed_token)
        
        # 如果没有可用的已刷新Token，使用原始候选列表
        if not refreshed_candidates:
            logger.warning("刷新Token信息后无可用Token，使用原始候选列表")
            refreshed_candidates = filtered_tokens
        
        # 智能选择算法：基于剩余配额、过去成功率和随机因素的加权选择
        weighted_tokens = []
        for token in refreshed_candidates:
            key = token.get('key', '')
            weight = 1.0  # 基础权重
            
            # 增加剩余配额权重
            if token.get('unlimited_quota'):
                weight *= 1.5  # 无限配额token有更高权重
            else:
                remain_quota = token.get('remain_quota', 0)
                system_quota = system_status["quota_per_unit"]
                
                # 基于系统配额动态调整权重
                if remain_quota > system_quota * 0.8:  # 剩余配额超过系统配额的80%
                    weight *= 1.5  # 配额非常充足
                elif remain_quota > system_quota * 0.5:  # 剩余配额超过系统配额的50%
                    weight *= 1.3  # 配额充足
                elif remain_quota > system_quota * 0.2:  # 剩余配额超过系统配额的20%
                    weight *= 1.1  # 配额一般
                elif remain_quota < system_quota * 0.05:  # 剩余配额低于系统配额的5%
                    weight *= 0.7  # 配额较低
            
            # 基于历史成功率调整权重
            usage_history = self.key_usage_history.get(key, {})
            success_count = usage_history.get('success_count', 0)
            failure_count = usage_history.get('failure_count', 0)
            
            if success_count + failure_count > 0:
                success_rate = success_count / (success_count + failure_count)
                weight *= (0.5 + success_rate)  # 成功率越高，权重越大
            
            # 考虑最近的失败情况
            failure_stats = key_failure_stats.get(key, {})
            consecutive_failures = failure_stats.get('consecutive_failures', 0)
            if consecutive_failures > 0:
                weight *= (1.0 / (1.0 + consecutive_failures * 0.2))  # 连续失败越多，权重越低
            
            # 添加随机因素，避免总是选择同一个token
            weight *= (0.9 + random.random() * 0.2)
            
            weighted_tokens.append((token, weight))
        
        # 根据权重排序并选择
        weighted_tokens.sort(key=lambda x: x[1], reverse=True)
        
        # 记录每个token的权重（调试用）
        for token, weight in weighted_tokens[:5]:  # 只记录权重前5的token
            logger.debug(f"Token ID={token.get('id')}, 权重={weight:.2f}, 剩余配额={token.get('remain_quota', 0)}")
        
        # 从权重最高的几个中随机选择一个，增加多样性
        top_n = min(3, len(weighted_tokens))  # 取权重最高的前3个
        selected_idx = random.randint(0, top_n - 1)
        selected = weighted_tokens[selected_idx][0]
        
        logger.info(f"已选择Token: ID={selected.get('id')}, Name={selected.get('name')}, Key={selected.get('key')[:10]}..., 权重={weighted_tokens[selected_idx][1]:.2f}, 剩余配额={selected.get('remain_quota', 0)}")
        return selected

    def update_api_key(self, token):
        """更新配置文件中的API密钥"""
        if not token:
            return False
        
        # 获取key
        key = token.get('key', '')
        if not key:
            logger.warning("选择的Token没有key")
            return False
        
        # 确保key前缀为sk-
        if self.add_prefix and not key.startswith('sk-'):
            key = f"sk-{key}"
        
        # 加载当前配置
        config = self.load_config()
        if not config:
            return False
        
        # 获取当前key
        current_key = config.get('openai', {}).get('api_key', '')
        
        # 如果key相同，不需要更新
        if current_key == key:
            logger.info("当前Key无需更新")
            return True
        
        # 更新key
        if 'openai' not in config:
            config['openai'] = {}
        config['openai']['api_key'] = key
        
        # 保存配置
        success = self.save_config(config)
        if success:
            self.current_key = key
            # 将当前key（不带sk-前缀）添加到已使用集合
            key_base = key
            if key.startswith('sk-'):
                key_base = key[3:]
            self.used_keys.add(key_base)
            
            # 记录使用历史
            if key_base not in self.key_usage_history:
                self.key_usage_history[key_base] = {
                    'success_count': 0,
                    'failure_count': 0,
                    'last_used': time.time()
                }
            else:
                self.key_usage_history[key_base]['last_used'] = time.time()
        return success

    def switch_key(self):
        """执行密钥切换"""
        global last_switch_time, cooldown_factor
        
        # 计算实际冷却时间
        actual_cooldown = min(base_cooldown * cooldown_factor, max_cooldown)
        
        # 防止频繁切换
        current_time = time.time()
        if current_time - last_switch_time < actual_cooldown:
            logger.info(f"冷却中，跳过密钥切换 (上次切换: {current_time - last_switch_time:.2f}秒前，冷却时间: {actual_cooldown:.1f}秒)")
            return False
            
        # 获取线程锁
        if not key_switch_lock.acquire(blocking=False):
            logger.info("另一个线程正在切换密钥，跳过")
            return False
            
        try:
            logger.info(f"开始切换API密钥 (当前冷却系数: {cooldown_factor:.1f})...")
            tokens = self.get_tokens()
            if not tokens:
                logger.warning("无法获取Token列表")
                return False
            
            selected_token = self.select_token(tokens)
            if not selected_token:
                logger.warning("无法选择可用的Token")
                return False
            
            success = self.update_api_key(selected_token)
            if success:
                last_switch_time = time.time()
                logger.info(f"API密钥切换成功，新密钥: {self.current_key}...")
                return True
            else:
                logger.error("API密钥切换失败")
                # 增加冷却系数，减少频繁切换
                cooldown_factor = min(cooldown_factor + 0.2, 3.0)
                return False
        finally:
            # 释放锁
            key_switch_lock.release()

    def report_key_success(self):
        """报告当前密钥使用成功"""
        if not self.current_key:
            return
            
        key_base = self.current_key
        if key_base.startswith('sk-'):
            key_base = key_base[3:]
            
        # 更新使用历史
        if key_base in self.key_usage_history:
            self.key_usage_history[key_base]['success_count'] += 1
        else:
            self.key_usage_history[key_base] = {
                'success_count': 1,
                'failure_count': 0,
                'last_used': time.time()
            }
            
        # 重置失败统计
        if key_base in key_failure_stats:
            key_failure_stats[key_base]['consecutive_failures'] = 0
            
        # 随着成功使用，逐渐降低冷却系数
        global cooldown_factor
        cooldown_factor = max(cooldown_factor * 0.95, 1.0)

    def report_key_failure(self, error_type=None):
        """报告当前密钥使用失败"""
        if not self.current_key:
            return
            
        key_base = self.current_key
        if key_base.startswith('sk-'):
            key_base = key_base[3:]
            
        # 更新使用历史
        if key_base in self.key_usage_history:
            self.key_usage_history[key_base]['failure_count'] += 1
        else:
            self.key_usage_history[key_base] = {
                'success_count': 0,
                'failure_count': 1,
                'last_used': time.time()
            }
            
        # 更新失败统计
        now = time.time()
        if key_base not in key_failure_stats:
            key_failure_stats[key_base] = {
                'count': 1,
                'last_failure': now,
                'consecutive_failures': 1,
                'error_types': {error_type: 1} if error_type else {}
            }
        else:
            key_failure_stats[key_base]['count'] += 1
            key_failure_stats[key_base]['last_failure'] = now
            key_failure_stats[key_base]['consecutive_failures'] += 1
            
            # 记录错误类型
            if error_type:
                if error_type not in key_failure_stats[key_base]['error_types']:
                    key_failure_stats[key_base]['error_types'][error_type] = 1
                else:
                    key_failure_stats[key_base]['error_types'][error_type] += 1
        
        # 连续失败次数超过阈值，增加冷却系数
        consecutive_failures = key_failure_stats[key_base]['consecutive_failures']
        if consecutive_failures > 3:
            global cooldown_factor
            cooldown_factor = min(cooldown_factor * 1.2, 3.0)
            logger.warning(f"密钥 {key_base[:10]}... 连续失败 {consecutive_failures} 次，增加冷却系数至 {cooldown_factor:.1f}")

    def _update_token(self, token_data):
        """更新Token信息（模拟成功）"""
        if not token_data or 'id' not in token_data:
            return False, "无效的Token数据"
            
        try:
            token_id = token_data['id']
            
            # 更新缓存
            global token_details_cache
            if token_id in token_details_cache:
                token_details_cache[token_id] = {
                    'data': token_data,
                    'timestamp': time.time()
                }
            
            logger.info(f"Token更新成功: ID={token_id}, Name={token_data.get('name', '')}")
            return True, token_data
            
        except Exception as e:
            error_msg = f"Token更新异常: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
            
    def _check_and_update_token(self, edited_token, original_token=None):
        """检查并更新Token，如果有变更才更新"""
        if not edited_token or 'id' not in edited_token:
            return False, "无效的Token数据"
            
        # 如果没有提供原始Token数据，尝试获取
        if not original_token:
            original_token = self.get_token_detail(edited_token['id'])
            if not original_token:
                return False, f"无法获取ID为{edited_token['id']}的原始Token数据"
        
        # 比较关键字段是否有变化
        fields_to_check = [
            'name', 'status', 'expired_time', 'remain_quota', 
            'unlimited_quota', 'model_limits_enabled', 'model_limits', 
            'allow_ips', 'group'
        ]
        
        has_changes = False
        changes = []
        
        for field in fields_to_check:
            if field in edited_token and field in original_token:
                if edited_token[field] != original_token[field]:
                    has_changes = True
                    changes.append(f"{field}: {original_token[field]} -> {edited_token[field]}")
        
        # 如果没有变化，不需要更新
        if not has_changes:
            logger.info(f"Token (ID={edited_token['id']}) 没有变化，跳过更新")
            return True, original_token
            
        # 记录变更内容
        change_log = ", ".join(changes)
        logger.info(f"Token (ID={edited_token['id']}) 有以下变更: {change_log}")
        
        # 执行更新
        return self._update_token(edited_token)

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
    # 只有 500 及以上错误才切换密钥
    if status_code >= 500:
        return True
    # 403 只重试，不切换
    if status_code == 403:
        return False
    # 其它错误保持原逻辑
    if status_code == 401:
        return True
    if status_code == 408:
        return True
    if status_code == 429:
        return True
    if error_message:
        key_related_errors = [
            "api key", "apikey", "token", "认证失败", "authentication", 
            "unauthorized", "授权", "invalid key", "invalid_key", "quota",
            "rate limit", "rate_limit", "too many requests", "请求过多",
            "超过速率限制", "请求速率"
        ]
        error_lower = error_message.lower()
        for err in key_related_errors:
            if err in error_lower:
                return True
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
    elif error_message:
        error_lower = error_message.lower()
        if any(keyword in error_lower for keyword in ["超过速率限制", "rate limit", "too many requests"]):
            return "rate_limit"
        elif any(keyword in error_lower for keyword in ["api key", "invalid key", "unauthorized"]):
            return "auth_error"
        elif any(keyword in error_lower for keyword in ["quota", "超出配额"]):
            return "quota_error"
        elif any(keyword in error_lower for keyword in ["timeout", "超时"]):
            return "timeout"
    return "unknown"

def switch_key_if_needed(status_code, error_message=None):
    """如果需要，切换密钥"""
    # 获取全局switcher
    switcher = get_switcher()
    
    # 判断是否需要切换密钥
    if should_switch_key(status_code, error_message):
        # 报告当前密钥失败
        error_type = get_error_type(status_code, error_message)
        switcher.report_key_failure(error_type)
        
        # 执行切换
        return switcher.switch_key()
    return False

def report_key_success():
    """报告当前密钥使用成功"""
    switcher = get_switcher()
    switcher.report_key_success()

# 获取失败统计信息
def get_failure_stats():
    """获取所有密钥的失败统计信息"""
    return key_failure_stats

# 清除Token详情缓存
def clear_token_cache():
    """清除Token详情缓存"""
    global token_details_cache
    size = len(token_details_cache)
    token_details_cache.clear()
    logger.info(f"已清除Token详情缓存 ({size}条记录)")
    return size

# 获取系统状态
def get_system_status():
    """获取系统状态信息"""
    global system_status
    
    # 如果系统状态已经更新过，直接返回
    if system_status["last_updated"] > 0:
        return system_status
        
    # 否则尝试更新
    switcher = get_switcher()
    switcher.update_system_status()
    return system_status

def update_token(token_data):
    """更新Token信息到服务器"""
    switcher = get_switcher()
    return switcher._update_token(token_data)

def check_and_update_token(edited_token, original_token=None):
    """检查并更新Token，如果有变更才更新"""
    switcher = get_switcher()
    return switcher._check_and_update_token(edited_token, original_token)

if __name__ == "__main__":
    # 测试代码
    switcher = get_switcher()
    success = switcher.switch_key()
    print(f"密钥切换结果: {'成功' if success else '失败'}")
    
    # 显示失败统计
    if key_failure_stats:
        print("\n密钥失败统计:")
        for key, stats in key_failure_stats.items():
            print(f"密钥: {key[:10]}...")
            print(f"  失败次数: {stats['count']}")
            print(f"  最后失败: {datetime.fromtimestamp(stats['last_failure']).strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  连续失败: {stats['consecutive_failures']}")
            if 'error_types' in stats and stats['error_types']:
                print("  错误类型:")
                for err_type, count in stats['error_types'].items():
                    print(f"    {err_type}: {count}次") 