# -*- coding: utf-8 -*-
"""
认证相关工具函数
"""
from functools import wraps
from flask import session, redirect, url_for, request

def login_required(view_func):
    """用户认证装饰器"""
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            # 用户未登录，重定向到登录页面
            return redirect(url_for('auth.login', next=request.path))
        return view_func(*args, **kwargs)
    return wrapped_view

def admin_required(view_func):
    """管理员权限装饰器"""
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get('is_admin', False):
            # 用户不是管理员，重定向到首页
            return redirect(url_for('index'))
        return view_func(*args, **kwargs)
    return wrapped_view
