# -*- coding: utf-8 -*-
"""
故障转移管理器
负责管理代理的故障转移策略和健康状态
"""

import time
import json
import threading
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from utils.logger import app_logger as logger

class FailoverManager:
    """故障转移管理器"""

    def __init__(self):
        self.enabled = True  # 默认启用故障转移
        self.proxy_health = {}  # 代理健康状态
        self.failure_counts = {}  # 失败计数
        self.last_check_time = {}  # 最后检查时间
        self.success_counts = {}  # 成功计数
        self.response_times = {}  # 响应时间记录
        self.lock = threading.Lock()

        # 故障转移配置
        self.max_failures = 3  # 最大失败次数
        self.failure_window = 300  # 失败窗口期（秒）
        self.recovery_time = 600  # 恢复时间（秒）
        self.circuit_breaker_threshold = 0.5  # 熔断器阈值（失败率）
        self.min_requests_for_circuit_breaker = 10  # 熔断器最小请求数

    def is_enabled(self) -> bool:
        """检查故障转移是否启用"""
        return self.enabled

    def enable_failover(self):
        """启用故障转移"""
        with self.lock:
            self.enabled = True
            logger.info("故障转移已启用")

    def disable_failover(self):
        """禁用故障转移"""
        with self.lock:
            self.enabled = False
            logger.info("故障转移已禁用")

    def toggle_failover(self) -> bool:
        """切换故障转移状态"""
        with self.lock:
            self.enabled = not self.enabled
            status = "启用" if self.enabled else "禁用"
            logger.info(f"故障转移已{status}")
            return self.enabled

    def record_success(self, proxy_name: str, response_time: float = None):
        """记录代理成功"""
        with self.lock:
            current_time = time.time()

            # 记录成功次数
            if proxy_name not in self.success_counts:
                self.success_counts[proxy_name] = []

            self.success_counts[proxy_name].append({
                'time': current_time,
                'response_time': response_time
            })

            # 清理过期的成功记录
            cutoff_time = current_time - self.failure_window
            self.success_counts[proxy_name] = [
                s for s in self.success_counts[proxy_name]
                if s['time'] > cutoff_time
            ]

            # 记录响应时间
            if response_time is not None:
                if proxy_name not in self.response_times:
                    self.response_times[proxy_name] = []

                self.response_times[proxy_name].append({
                    'time': current_time,
                    'response_time': response_time
                })

                # 只保留最近100次响应时间
                if len(self.response_times[proxy_name]) > 100:
                    self.response_times[proxy_name] = self.response_times[proxy_name][-100:]

            # 更新健康状态
            self.proxy_health[proxy_name] = {
                'status': 'healthy',
                'last_success': datetime.now().isoformat(),
                'consecutive_failures': 0,
                'total_successes': len(self.success_counts[proxy_name])
            }

            logger.info(f"代理 {proxy_name} 成功记录，响应时间: {response_time}ms")

    def record_failure(self, proxy_name: str, error_message: str = None):
        """记录代理失败"""
        with self.lock:
            current_time = time.time()

            # 初始化失败记录
            if proxy_name not in self.failure_counts:
                self.failure_counts[proxy_name] = []

            # 添加失败记录
            self.failure_counts[proxy_name].append({
                'time': current_time,
                'error': error_message
            })

            # 清理过期的失败记录
            cutoff_time = current_time - self.failure_window
            self.failure_counts[proxy_name] = [
                f for f in self.failure_counts[proxy_name]
                if f['time'] > cutoff_time
            ]

            # 更新健康状态
            failure_count = len(self.failure_counts[proxy_name])
            consecutive_failures = self.proxy_health.get(proxy_name, {}).get('consecutive_failures', 0) + 1

            self.proxy_health[proxy_name] = {
                'status': 'unhealthy' if failure_count >= self.max_failures else 'degraded',
                'last_failure': datetime.now().isoformat(),
                'consecutive_failures': consecutive_failures,
                'recent_failures': failure_count,
                'last_error': error_message
            }

            logger.warning(f"代理 {proxy_name} 失败记录: {failure_count}/{self.max_failures}")

    def is_proxy_healthy(self, proxy_name: str) -> bool:
        """检查代理是否健康（包含熔断器逻辑）"""
        if not self.enabled:
            return True  # 如果故障转移被禁用，认为所有代理都健康

        with self.lock:
            # 检查是否在恢复期
            if proxy_name in self.proxy_health:
                health_info = self.proxy_health[proxy_name]
                if health_info['status'] == 'unhealthy':
                    # 检查是否已过恢复时间
                    if 'last_failure' in health_info:
                        last_failure = datetime.fromisoformat(health_info['last_failure'])
                        if datetime.now() - last_failure > timedelta(seconds=self.recovery_time):
                            # 重置健康状态，给代理一次恢复机会
                            self.proxy_health[proxy_name]['status'] = 'recovering'
                            logger.info(f"代理 {proxy_name} 进入恢复状态")
                            return True
                    return False

            # 熔断器检查
            if self._is_circuit_breaker_open(proxy_name):
                logger.warning(f"代理 {proxy_name} 熔断器开启，暂时不可用")
                return False

            # 检查最近失败次数
            if proxy_name in self.failure_counts:
                current_time = time.time()
                cutoff_time = current_time - self.failure_window
                recent_failures = [
                    f for f in self.failure_counts[proxy_name]
                    if f['time'] > cutoff_time
                ]
                return len(recent_failures) < self.max_failures

            return True

    def _is_circuit_breaker_open(self, proxy_name: str) -> bool:
        """检查熔断器是否开启"""
        current_time = time.time()
        cutoff_time = current_time - self.failure_window

        # 获取最近的成功和失败次数
        recent_failures = 0
        if proxy_name in self.failure_counts:
            recent_failures = len([
                f for f in self.failure_counts[proxy_name]
                if f['time'] > cutoff_time
            ])

        recent_successes = 0
        if proxy_name in self.success_counts:
            recent_successes = len([
                s for s in self.success_counts[proxy_name]
                if s['time'] > cutoff_time
            ])

        total_requests = recent_failures + recent_successes

        # 如果请求数不足，不启用熔断器
        if total_requests < self.min_requests_for_circuit_breaker:
            return False

        # 计算失败率
        failure_rate = recent_failures / total_requests

        # 如果失败率超过阈值，开启熔断器
        if failure_rate >= self.circuit_breaker_threshold:
            logger.warning(f"代理 {proxy_name} 失败率 {failure_rate:.2%} 超过阈值 {self.circuit_breaker_threshold:.2%}")
            return True

        return False

    def get_healthy_proxies(self, proxy_names: List[str]) -> List[str]:
        """获取健康的代理列表"""
        return [name for name in proxy_names if self.is_proxy_healthy(name)]

    def get_proxy_health_status(self, proxy_name: str) -> Dict:
        """获取代理健康状态详情"""
        with self.lock:
            current_time = time.time()
            cutoff_time = current_time - self.failure_window

            if proxy_name not in self.proxy_health:
                return {
                    'status': 'unknown',
                    'consecutive_failures': 0,
                    'recent_failures': 0,
                    'recent_successes': 0,
                    'success_rate': 0.0,
                    'avg_response_time': 0.0,
                    'circuit_breaker_open': False
                }

            health_info = self.proxy_health[proxy_name].copy()

            # 计算最近失败次数
            recent_failures = 0
            if proxy_name in self.failure_counts:
                recent_failures = len([
                    f for f in self.failure_counts[proxy_name]
                    if f['time'] > cutoff_time
                ])
            health_info['recent_failures'] = recent_failures

            # 计算最近成功次数
            recent_successes = 0
            if proxy_name in self.success_counts:
                recent_successes = len([
                    s for s in self.success_counts[proxy_name]
                    if s['time'] > cutoff_time
                ])
            health_info['recent_successes'] = recent_successes

            # 计算成功率
            total_requests = recent_failures + recent_successes
            if total_requests > 0:
                health_info['success_rate'] = (recent_successes / total_requests) * 100
            else:
                health_info['success_rate'] = 0.0

            # 计算平均响应时间
            if proxy_name in self.response_times and self.response_times[proxy_name]:
                recent_response_times = [
                    rt['response_time'] for rt in self.response_times[proxy_name]
                    if rt['time'] > cutoff_time and rt['response_time'] is not None
                ]
                if recent_response_times:
                    health_info['avg_response_time'] = sum(recent_response_times) / len(recent_response_times)
                else:
                    health_info['avg_response_time'] = 0.0
            else:
                health_info['avg_response_time'] = 0.0

            # 检查熔断器状态
            health_info['circuit_breaker_open'] = self._is_circuit_breaker_open(proxy_name)

            return health_info

    def get_all_health_status(self) -> Dict:
        """获取所有代理的健康状态"""
        with self.lock:
            return {
                'enabled': self.enabled,
                'proxies': {name: self.get_proxy_health_status(name) for name in self.proxy_health.keys()},
                'config': {
                    'max_failures': self.max_failures,
                    'failure_window': self.failure_window,
                    'recovery_time': self.recovery_time
                }
            }

    def reset_proxy_health(self, proxy_name: str):
        """重置代理健康状态"""
        with self.lock:
            if proxy_name in self.proxy_health:
                del self.proxy_health[proxy_name]
            if proxy_name in self.failure_counts:
                del self.failure_counts[proxy_name]
            logger.info(f"已重置代理 {proxy_name} 的健康状态")

    def reset_all_health(self):
        """重置所有代理健康状态"""
        with self.lock:
            self.proxy_health.clear()
            self.failure_counts.clear()
            logger.info("已重置所有代理的健康状态")

# 全局故障转移管理器实例
_failover_manager = None

def get_failover_manager() -> FailoverManager:
    """获取故障转移管理器单例"""
    global _failover_manager
    if _failover_manager is None:
        _failover_manager = FailoverManager()
    return _failover_manager
