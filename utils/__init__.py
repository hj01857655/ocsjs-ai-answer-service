# -*- coding: utf-8 -*-
"""
工具函数包

包含以下工具模块：
- utils.py: 通用工具函数（格式化、解析等）
- auth.py: 认证相关工具（登录验证、权限检查）
- logger.py: 日志工具
- question_cleaner.py: 题目清理工具
- get_models_list.py: 获取第三方API模型列表工具（独立脚本）
- clean_question_prefixes.py: 题目前缀清理工具（数据库维护脚本）
"""

from .utils import (
    format_answer_for_ocs,
    parse_question_and_options,
    extract_answer,
    SimpleCache
)
from .logger import app_logger
from .auth import login_required, admin_required

# 导出所有工具函数
__all__ = [
    'format_answer_for_ocs',
    'parse_question_and_options',
    'extract_answer',
    'SimpleCache',
    'app_logger',
    'login_required',
    'admin_required'
]
