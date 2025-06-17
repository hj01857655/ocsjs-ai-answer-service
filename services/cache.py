# -*- coding: utf-8 -*-
"""
Redis缓存实现
"""
import redis
import hashlib
from config import Config

class RedisCache:
    """Redis缓存实现"""
    
    def __init__(self, expiration=86400):
        """初始化Redis连接"""
        self.redis = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            password=Config.REDIS_PASSWORD,
            db=Config.REDIS_DB,
            decode_responses=True
        )
        self.expiration = expiration
    
    def _generate_key(self, question, question_type=None, options=None):
        """生成缓存键"""
        # 使用问题、类型和选项组合生成唯一键
        content = f"{question}_{question_type or ''}_{options or ''}"
        # 使用MD5生成固定长度的键
        return f"qa_cache:{hashlib.md5(content.encode()).hexdigest()}"
    
    def get(self, question, question_type=None, options=None):
        """获取缓存"""
        key = self._generate_key(question, question_type, options)
        cached = self.redis.get(key)
        if cached:
            return cached
        return None
    
    def set(self, question, answer, question_type=None, options=None):
        """设置缓存"""
        key = self._generate_key(question, question_type, options)
        self.redis.setex(key, self.expiration, answer)
        return True
    
    def delete(self, question, question_type=None, options=None):
        """删除缓存"""
        key = self._generate_key(question, question_type, options)
        return self.redis.delete(key)
    
    def clear(self):
        """清除所有缓存"""
        # 获取所有缓存键
        keys = self.redis.keys("qa_cache:*")
        if keys:
            return self.redis.delete(*keys)
        return 0
    
    @property
    def size(self):
        """获取缓存大小"""
        return len(self.redis.keys("qa_cache:*")) 