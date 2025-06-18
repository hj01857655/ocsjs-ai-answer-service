import json
import os
from flask import Blueprint, render_template, request, session, redirect
from datetime import datetime
from functools import wraps
# provider 相关导入已移除

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')

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

settings_bp = Blueprint('settings', __name__)

def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    current_year = datetime.now().year
    config = load_config()
    # 构造 current_config 供前端渲染
    current_config = {
        'service': config.get('service', {}),
        'third_party_apis': config.get('third_party_apis', []),
        'cache': config.get('cache', {}),
        'database': config.get('database', {}),
        'redis': config.get('redis', {}),
        'record': config.get('record', {}),
        'security': config.get('security', {}),

        # provider 相关字段已移除
    }
    if request.method == 'POST':
        try:
            # 只允许编辑 third_party_apis、cache、database、redis、record
            # 注意：第三方API代理池配置现在是只读的，需要直接编辑config.json
            # 这里保持向后兼容，但实际上不会修改数组结构
            # cache
            cache = config.get('cache', {})
            cache['enable'] = request.form.get('cache_enable') == 'on'
            cache['expiration'] = int(request.form.get('cache_expiration', cache.get('expiration', 2592000)))
            config['cache'] = cache
            # database
            database = config.get('database', {})
            database['host'] = request.form.get('db_host', database.get('host', ''))
            database['port'] = int(request.form.get('db_port', database.get('port', 3306)))
            database['user'] = request.form.get('db_user', database.get('user', ''))
            database['password'] = request.form.get('db_password', database.get('password', ''))
            database['name'] = request.form.get('db_name', database.get('name', ''))
            config['database'] = database
            # redis
            redis = config.get('redis', {})
            redis['enabled'] = request.form.get('redis_enabled') == 'on'
            redis['host'] = request.form.get('redis_host', redis.get('host', ''))
            redis['port'] = int(request.form.get('redis_port', redis.get('port', 6379)))
            redis['password'] = request.form.get('redis_password', redis.get('password', ''))
            redis['db'] = int(request.form.get('redis_db', redis.get('db', 0)))
            config['redis'] = redis
            # record
            record = config.get('record', {})
            record['enable'] = request.form.get('record_enable') == 'on'
            config['record'] = record
            save_config(config)
            success = request.args.get('success', False)
            message = request.args.get('message', '')

            return render_template('settings.html',
                                   config=current_config,
                                   current_year=current_year,
                                   success=success,
                                   message=message)
        except Exception as e:
            return render_template('settings.html', error=f"更新配置失败: {str(e)}", config=current_config, current_year=current_year)
    success = request.args.get('success', False)
    message = request.args.get('message', '')

    # Provider 相关代码已移除

    return render_template('settings.html',
                           config=current_config,
                           current_year=current_year,
                           success=success,
                           message=message)