# -*- coding: utf-8 -*-
"""
工具函数模块
包含缓存管理、答案处理和OpenAI API调用等辅助功能
"""
import time
import hashlib
from typing import Dict, Any, Optional
from flask import session, redirect, render_template
from functools import wraps

class SimpleCache:
    """简单的内存缓存实现"""

    def __init__(self, expiration_seconds: int = 86400):
        """
        初始化缓存

        Args:
            expiration_seconds: 缓存过期时间（秒），默认24小时
        """
        self.cache = {}
        self.expiration = expiration_seconds

    def _generate_key(self, question: str, question_type: str, options: str) -> str:
        """
        根据问题内容生成缓存键

        Args:
            question: 问题内容
            question_type: 问题类型
            options: 选项内容

        Returns:
            str: 缓存键
        """
        # 使用问题内容、类型和选项的组合生成哈希键
        content = f"{question}|{question_type}|{options}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def get(self, question: str, question_type: str = "", options: str = "") -> Optional[str]:
        """
        从缓存获取答案

        Args:
            question: 问题内容
            question_type: 问题类型
            options: 选项内容

        Returns:
            Optional[str]: 缓存的答案，如果不存在或已过期则返回None
        """
        key = self._generate_key(question, question_type, options)
        if key in self.cache:
            timestamp, value = self.cache[key]
            # 检查缓存是否过期
            if time.time() - timestamp < self.expiration:
                return value
            # 缓存已过期，删除
            del self.cache[key]
        return None

    def set(self, question: str, answer: str, question_type: str = "", options: str = "") -> None:
        """
        设置缓存

        Args:
            question: 问题内容
            answer: 答案内容
            question_type: 问题类型
            options: 选项内容
        """
        key = self._generate_key(question, question_type, options)
        self.cache[key] = (time.time(), answer)

    def clear(self) -> None:
        """清空所有缓存"""
        self.cache.clear()

    def remove_expired(self) -> int:
        """
        删除所有过期的缓存项

        Returns:
            int: 删除的缓存项数量
        """
        now = time.time()
        expired_keys = [
            key for key, (timestamp, _) in self.cache.items()
            if now - timestamp >= self.expiration
        ]

        for key in expired_keys:
            del self.cache[key]

        return len(expired_keys)


def format_answer_for_ocs(question: str, answer: str) -> Dict[str, Any]:
    """
    格式化答案为OCS期望的格式

    Args:
        question: 问题内容
        answer: 答案内容

    Returns:
        Dict[str, Any]: 格式化后的响应
    """
    return {
        'code': 1,
        'question': question,
        'answer': answer
    }


def parse_question_and_options(question: str, options: str, question_type: str) -> str:
    """
    解析问题和选项，为第三方AI API构建更好的提示

    Args:
        question: 问题内容
        options: 选项内容
        question_type: 问题类型（单选、多选、判断、填空）

    Returns:
        str: 格式化后的提示
    """
    prompt = f"问题: {question}\n"

    # 添加题目类型提示
    type_prompts = {
        "single": "这是一道单选题。",
        "multiple": "这是一道多选题，答案请用#符号分隔。",
        "judgement": "这是一道判断题，需要回答：正确/对/true/√ 或者 错误/错/false/×。",
        "completion": "这是一道填空题。"
    }

    if question_type in type_prompts:
        prompt += f"{type_prompts[question_type]}\n"

    if options:
        prompt += f"选项:\n{options}\n"

    prompt += "请直接给出答案，不要解释。"
    return prompt


def extract_answer(ai_response: str, question_type: str) -> str:
    """
    从AI响应中提取答案

    Args:
        ai_response: AI生成的完整响应
        question_type: 问题类型

    Returns:
        str: 提取的答案部分
    """
    if not ai_response or not ai_response.strip():
        return ai_response

    # 清理响应内容
    response = ai_response.strip()

    # 对于选择题，检查是否返回了选项字母而不是内容
    if question_type in ["single", "multiple"]:
        # 检查是否只返回了选项字母（如 "C" 或 "A#B#C"）
        if question_type == "single":
            # 单选题：检查是否只返回了单个字母
            if len(response) == 1 and response.upper() in ['A', 'B', 'C', 'D', 'E', 'F']:
                # 这种情况说明AI只返回了选项字母，需要在系统提示中强调返回选项内容
                # 暂时返回原始响应，但记录警告
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"AI返回了选项字母而非内容: {response}")
                return response
        elif question_type == "multiple":
            # 多选题：确保答案格式正确（使用#分隔）
            # 检查是否是字母格式（如 "A,B,C" 或 "ABC"）
            letters_only = all(c.upper() in 'ABCDEF,#，、 ' for c in response)
            if letters_only and any(c.upper() in 'ABCDEF' for c in response):
                # 提取字母并用#连接
                import re
                letters = re.findall(r'[A-F]', response.upper())
                if letters:
                    return '#'.join(letters)

            # 如果响应中包含选项内容但没有#分隔符，尝试智能分割
            if '#' not in response and any(keyword in response for keyword in ['、', '；', ';', '和', '以及']):
                # 尝试用常见分隔符分割
                for sep in ['、', '；', ';', '和', '以及']:
                    if sep in response:
                        parts = [part.strip() for part in response.split(sep) if part.strip()]
                        if len(parts) > 1:
                            return '#'.join(parts)

    # 对于判断题，标准化答案格式
    elif question_type == "judgement":
        response_lower = response.lower()
        # 正确的表示
        if any(word in response_lower for word in ['正确', '对', 'true', '√', 'yes', '是']):
            return '正确'
        # 错误的表示
        elif any(word in response_lower for word in ['错误', '错', 'false', '×', 'no', '否']):
            return '错误'

    # 默认返回清理后的响应
    return response

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return view_func(*args, **kwargs)
    return wrapped_view

def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        if not session.get('is_admin', False):
            return render_template('error.html', error="您没有管理员权限访问此页面")
        return view_func(*args, **kwargs)
    return wrapped_view