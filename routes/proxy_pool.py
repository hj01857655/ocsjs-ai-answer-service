from flask import Blueprint, render_template
from config import Config
from config.api_proxy_pool import get_api_proxy_pool
import time
from utils import login_required, admin_required

proxy_pool_bp = Blueprint('proxy_pool', __name__)

@proxy_pool_bp.route('/tokens', methods=['GET'])
@proxy_pool_bp.route('/proxy-monitor', methods=['GET'])
@login_required
@admin_required
def proxy_monitor():
    current_year = time.localtime().tm_year
    uptime_seconds = time.time() - 0
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    uptime_str = f"{days}天{hours}小时{minutes}分钟"

    # 获取代理池信息
    try:
        proxy_pool = get_api_proxy_pool()
        proxy_stats = proxy_pool.get_proxy_stats()
        all_models = proxy_pool.get_all_models()
        available_models = all_models[:5] if all_models else []
    except Exception as e:
        proxy_stats = {
            'total_proxies': 0,
            'active_proxies': 0,
            'total_api_keys': 0,
            'total_models': 0
        }
        available_models = []

    # 获取当前使用的代理信息
    try:
        from config.api_proxy_pool import get_api_proxy_pool
        proxy_pool = get_api_proxy_pool()
        primary_proxy = proxy_pool.get_primary_proxy()
        current_model = primary_proxy.model if primary_proxy else "未配置代理"
    except Exception:
        current_model = "代理池未初始化"

    return render_template(
        'proxy_pool.html',
        version="2.0.0",
        model=current_model,
        uptime=uptime_str,
        current_year=current_year,
        available_models=available_models,
        proxy_stats=proxy_stats
    )

