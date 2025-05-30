from flask import Blueprint, render_template
from config import Config
import time
from utils import login_required, admin_required

token_bp = Blueprint('token', __name__)

@token_bp.route('/tokens', methods=['GET'])
@login_required
@admin_required
def tokens_monitor():
    current_year = time.localtime().tm_year
    uptime_seconds = time.time() - 0
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    uptime_str = f"{days}天{hours}小时{minutes}分钟"
    available_models = ["gpt-4o", "gpt-4.1-mini", "gpt-4.1-nano"]
    # 只读页面不再传递 tokens
    return render_template(
        'tokens.html',
        version="1.1.0",
        model=Config.OPENAI_MODEL,
        uptime=uptime_str,
        current_year=current_year,
        available_models=available_models
    )

