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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/key_switcher.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('key_switcher')

# 确保日志目录存在
if not os.path.exists('logs'):
    os.makedirs('logs')

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

class KeySwitcher:
    def __init__(self, config_file='config.json', add_prefix=True):
        self.config_file = config_file
        self.add_prefix = add_prefix
        self.session = requests.Session()
        self.current_key = None
        self.used_keys = set()  # 记录已使用过的key
        self.key_usage_history = {}  # 记录key的使用历史: {key: {"success_count": 0, "failure_count": 0, "last_used": timestamp}}
        self.load_current_key()
    
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

    def get_tokens(self):
        """从本地API获取可用的token列表"""
        try:
            # 先登录获取会话cookie
            login_data = {"username": "admin", "password": "admin123"}
            self.session.post('http://localhost:5000/login', data=login_data)
            
            # 获取token列表
            response = self.session.get('http://localhost:5000/api/token/?p=0&size=50')  # 增加获取的token数量
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    return data['data']
            logger.error(f"获取Token失败: {response.status_code} - {response.text}")
            return []
        except Exception as e:
            logger.error(f"获取Token出错: {e}")
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
        
        # 过滤掉配额用完的token
        quota_tokens = [t for t in valid_tokens if t.get('unlimited_quota') or t.get('remain_quota', 0) > 0]
        
        if not quota_tokens:
            logger.warning("所有Token配额已用完")
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
        
        # 智能选择算法：基于剩余配额、过去成功率和随机因素的加权选择
        weighted_tokens = []
        for token in filtered_tokens:
            key = token.get('key', '')
            weight = 1.0  # 基础权重
            
            # 增加剩余配额权重
            if token.get('unlimited_quota'):
                weight *= 1.5  # 无限配额token有更高权重
            else:
                remain_quota = token.get('remain_quota', 0)
                if remain_quota > 100000:
                    weight *= 1.3  # 配额充足
                elif remain_quota > 10000:
                    weight *= 1.1  # 配额一般
            
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
            logger.debug(f"Token ID={token.get('id')}, 权重={weight:.2f}")
        
        # 从权重最高的几个中随机选择一个，增加多样性
        top_n = min(3, len(weighted_tokens))  # 取权重最高的前3个
        selected_idx = random.randint(0, top_n - 1)
        selected = weighted_tokens[selected_idx][0]
        
        logger.info(f"已选择Token: ID={selected.get('id')}, Name={selected.get('name')}, Key={selected.get('key')[:10]}..., 权重={weighted_tokens[selected_idx][1]:.2f}")
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
                logger.info(f"API密钥切换成功，新密钥: {self.current_key[:10]}...")
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
    # 服务器错误或超时，需要切换
    if status_code >= 500:
        return True
    
    # 密钥相关错误
    if status_code == 401 or status_code == 403:
        return True
    
    # 请求超时
    if status_code == 408:
        return True
    
    # 速率限制错误
    if status_code == 429:
        return True
    
    # 如果有错误消息，检查是否与密钥相关
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