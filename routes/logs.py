from flask import Blueprint, render_template, request, jsonify
from datetime import datetime
import os
import glob
from utils.logger import Logger
from config import Config
from utils import login_required, admin_required

logs_bp = Blueprint('logs', __name__)

@logs_bp.route('/logs', methods=['GET'])
@login_required
@admin_required
def logs_panel():
    current_year = datetime.now().year
    log_content = Logger.get_latest_logs(max_lines=2000)
    uptime_seconds = 0  # 可根据实际需要传递
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    uptime_str = f"{days}天{hours}小时{minutes}分钟"
    if request.args.get('ajax'):
        return render_template(
            'logs.html',
            version="1.1.0",
            log_content=log_content,
            model=Config.OPENAI_MODEL,
            uptime=uptime_str,
            current_year=current_year
        )
    return render_template(
        'logs.html',
        version="1.1.0",
        log_content=log_content,
        model=Config.OPENAI_MODEL,
        uptime=uptime_str,
        current_year=current_year
    )

@logs_bp.route('/api/logs/clear', methods=['POST'])
@login_required
@admin_required
def clear_logs():
    """清空日志文件"""
    try:
        # 确保日志目录存在
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            return jsonify({"success": True, "message": "创建了日志目录，但没有日志文件需要清空"})
        
        # 获取所有日志文件
        log_files = glob.glob(os.path.join(log_dir, "*.log"))
        log_files.extend(glob.glob(os.path.join(log_dir, "*.log.*")))
        
        if not log_files:
            return jsonify({"success": False, "message": "未找到日志文件"})
        
        # 记录清空和失败的文件
        cleared_files = []
        failed_files = []
        error_messages = []
        
        for log_file in log_files:
            try:
                # 尝试关闭可能打开的文件句柄 
                try:
                    import psutil
                    for proc in psutil.process_iter(['pid', 'open_files']):
                        try:
                            for file in proc.info['open_files'] or []:
                                if file.path == os.path.abspath(log_file):
                                    print(f"文件 {log_file} 被进程 {proc.pid} 占用，尝试其他方法")
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except ImportError:
                    print("psutil模块不可用，跳过进程检查")
                
                # 尝试使用低级文件操作
                try:
                    # 方法1: 使用truncate清空文件
                    with open(log_file, 'r+', encoding='utf-8') as f:
                        f.truncate(0)
                        f.write(f"--- 日志已清空 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                    cleared_files.append(log_file)
                except Exception as e1:
                    try:
                        # 方法2: 尝试删除并重新创建文件
                        os.remove(log_file)
                        with open(log_file, 'w', encoding='utf-8') as f:
                            f.write(f"--- 日志已清空 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                        cleared_files.append(log_file)
                    except Exception as e2:
                        # 两种方法都失败
                        failed_files.append(log_file)
                        error_messages.append(f"{log_file}: {str(e1)} | {str(e2)}")
            except Exception as e:
                failed_files.append(log_file)
                error_messages.append(f"{log_file}: {str(e)}")
        
        # 根据结果返回相应的消息
        if cleared_files and not failed_files:
            return jsonify({
                "success": True, 
                "message": f"成功清空 {len(cleared_files)} 个日志文件"
            })
        elif cleared_files and failed_files:
            return jsonify({
                "success": True, 
                "message": f"部分成功: 清空了 {len(cleared_files)} 个文件，{len(failed_files)} 个文件失败",
                "details": error_messages
            })
        else:
            return jsonify({
                "success": False, 
                "message": f"清空失败: 所有 {len(failed_files)} 个文件均无法清空",
                "details": error_messages
            }), 500
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return jsonify({
            "success": False, 
            "message": f"清空日志文件失败: {str(e)}",
            "details": error_details
        }), 500