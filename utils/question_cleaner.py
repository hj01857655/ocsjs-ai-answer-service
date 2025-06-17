#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
题目前缀清理工具
用于清理题目前缀，如"20. (单选题，1分)"和"55. (判断题，1分)"
"""

import re
import logging

logger = logging.getLogger('question_cleaner')

def clean_question_prefix(question_text):
    """
    清理题目前缀
    :param question_text: 原始题目文本
    :return: 清理后的题目文本
    """
    if not question_text:
        return question_text
    
    # 保存原始内容用于日志记录
    original_content = question_text
    
    # 先尝试去除常见的序号+题型前缀格式
    question_text = re.sub(r'^\s*\d+\.?\s*[\(\uff08][^\)\uff09]+[\)\uff09]\s*', '', question_text, flags=re.I)
    
    # 再尝试去除可能的其他格式前缀
    question_text = re.sub(r'^\s*\d+\.?\s*', '', question_text, flags=re.I)  # 去除只有序号的前缀
    question_text = re.sub(r'^\s*[\(\uff08][^\)\uff09]+[\)\uff09]\s*', '', question_text, flags=re.I)  # 去除只有括号的前缀
    
    # 去除可能的空格
    question_text = question_text.strip()
    
    # 如果内容发生了变化，记录日志
    if original_content != question_text:
        logger.debug(f'题目前缀去除: 原始="{original_content[:50]}..." → 处理后="{question_text[:50]}..."')
    
    return question_text
