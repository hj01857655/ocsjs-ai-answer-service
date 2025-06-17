import json
import os
from flask import Blueprint, render_template, request, session, redirect
from datetime import datetime
from functools import wraps
from config.model_providers import provider_manager, load_providers_from_file

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
        'openai': config.get('openai', {}),
        'cache': config.get('cache', {}),
        'database': config.get('database', {}),
        'redis': config.get('redis', {}),
        'record': config.get('record', {}),
        'security': config.get('security', {}),
        
        # 获取模型供应商信息
        'model_providers': [],
        'default_provider': ''
    }
    if request.method == 'POST':
        try:
            # 只允许编辑 openai、cache、database、redis、record
            # openai
            openai = config.get('openai', {})
            openai['api_key'] = request.form.get('openai_api_key', openai.get('api_key', ''))
            openai['session'] = request.form.get('openai_session', openai.get('session', ''))
            openai['api_base'] = request.form.get('openai_api_base', openai.get('api_base', ''))
            openai['model'] = request.form.get('openai_model', openai.get('model', ''))
            openai['models'] = request.form.getlist('openai_models') or openai.get('models', [])
            config['openai'] = openai
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
            
            # 获取模型供应商信息
            providers = provider_manager.get_all_providers()
            model_providers = []
            for provider in providers:
                model_providers.append({
                    'provider_id': provider.provider_id,
                    'name': provider.name,
                    'api_key': provider.api_key,
                    'api_base': provider.api_base,
                    'models': provider.models,
                    'default_model': provider.default_model,
                    'is_active': provider.is_active,
                    'parameters': provider.parameters
                })
            default_provider = provider_manager.get_default_provider_id()
            
            return render_template('settings.html', 
                                   config=current_config,
                                   model_providers=model_providers,
                                   default_provider=default_provider,
                                   current_year=current_year, 
                                   success=success, 
                                   message=message)
        except Exception as e:
            return render_template('settings.html', error=f"更新配置失败: {str(e)}", config=current_config, current_year=current_year)
    success = request.args.get('success', False)
    message = request.args.get('message', '')
    
    # 获取模型供应商信息
    providers = provider_manager.get_all_providers()
    model_providers = []
    for provider in providers:
        # 确保provider_id是字符串
        provider_id = str(provider.provider_id) if provider.provider_id is not None else ''
        model_providers.append({
            'provider_id': provider_id,
            'name': provider.name,
            'api_key': provider.api_key,
            'api_base': provider.api_base,
            'models': provider.models,
            'default_model': provider.default_model,
            'is_active': provider.is_active,
            'parameters': provider.parameters
        })
    default_provider = provider_manager.get_default_provider_id()
    # 确保default_provider是字符串
    default_provider = str(default_provider) if default_provider is not None else ''
    
    return render_template('settings.html', 
                           config=current_config,
                           model_providers=model_providers,
                           default_provider=default_provider,
                           current_year=current_year, 
                           success=success, 
                           message=message)