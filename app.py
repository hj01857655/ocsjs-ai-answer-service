# -*- coding: utf-8 -*-
"""
EduBrain AI - 智能题库系统
基于第三方AI API的智能题库服务，提供兼容 OCS 接口的智能答题功能
支持多代理池、自动故障转移和负载均衡
作者：Lynn
版本：2.0.0
"""

import os
import time
import logging
from datetime import datetime
import functools
import random

from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS

# 抑制SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from config import Config
from utils import format_answer_for_ocs, parse_question_and_options, extract_answer
from models import QARecord, UserSession, get_db_session, close_db_session, get_user_by_id
from services import RedisCache
# 移除旧的provider_manager和key_switcher，直接使用代理池系统
from services.model_service import SyncModelService
from routes.auth import auth_bp
from routes.proxy_pool import proxy_pool_bp
from routes.questions import questions_bp
from routes.settings import settings_bp
from routes.logs import logs_bp
from routes.image_proxy import register_image_proxy_bp
from routes.proxy_management import proxy_management_bp
# 移除了 sync_tokens_to_config 和 BackgroundScheduler 导入 - 不再需要

# 配置日志系统
if not os.path.exists('logs'):
    os.makedirs('logs')

# 配置主日志文件
log_file = os.path.join('logs', 'app.log')
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(getattr(logging, Config.LOG_LEVEL))
file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_format)

# 移除所有根日志记录器的处理器
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# 配置根日志记录器，只输出到文件，不输出到控制台
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[file_handler]
)

# 禁用控制台输出
logging.root.handlers = [file_handler]

# 禁用Flask自带的werkzeug日志记录器，仅显示ERROR级别
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)
werkzeug_logger.propagate = False
werkzeug_logger.handlers = []
werkzeug_logger.addHandler(file_handler)

# 禁用httpx库的日志输出到控制台，但保留到文件
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.INFO)
httpx_logger.propagate = False  # 不传播到父记录器
httpx_logger.handlers = []
httpx_logger.addHandler(file_handler)

httpcore_logger = logging.getLogger("httpcore")
httpcore_logger.setLevel(logging.INFO)
httpcore_logger.propagate = False  # 不传播到父记录器
httpcore_logger.handlers = []
httpcore_logger.addHandler(file_handler)

# 应用日志记录器
logger = logging.getLogger('ai_answer_service')
logger.propagate = False  # 不传播到父记录器
logger.handlers = []
logger.addHandler(file_handler)

# 记录应用启动时间（全局变量）
# 使用模块级别的变量确保在所有情况下都能访问
import sys
if not hasattr(sys.modules[__name__], 'start_time'):
    start_time = time.time()
else:
    start_time = getattr(sys.modules[__name__], 'start_time', time.time())

# 初始化应用
app = Flask(__name__)
# 使用更宽松的CORS配置，允许所有来源的请求
# 这对于开发和测试非常有用，但在生产环境中应该更加限制
CORS(app,
     supports_credentials=True,
     origins=["https://mooc2-ans.chaoxing.com", "http://localhost:8080", "http://127.0.0.1:8080"],  # 指定允许的来源
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"],  # 指定允许的头信息
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     expose_headers=["Content-Length", "X-Total-Count"],
     max_age=600  # 预检请求缓存时间，减少OPTIONS请求
)

# 设置应用密钥，用于会话加密
app.secret_key = Config.SECRET_KEY if hasattr(Config, 'SECRET_KEY') else os.urandom(24)

# 禁用Flask内置日志，仅保留错误级别
app.logger.setLevel(logging.ERROR)
app.logger.propagate = False
app.logger.handlers = []
app.logger.addHandler(file_handler)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# 全局变量
from flask import g

# 请求级别的数据库会话管理
@app.before_request
def setup_request():
    """在每个请求前创建一个新的数据库会话"""
    try:
        session = get_db_session()
        if session is None:
            logger.error("无法创建数据库会话，请检查数据库连接")
            # 在这里不抛出异常，而是允许请求继续处理
            # 其他需要数据库的代码应该检查g.db是否存在
        g.db = session
        logger.debug("成功创建请求级别的数据库会话")
    except Exception as e:
        logger.error(f"初始化请求级别的数据库会话时出错: {str(e)}")
        # 设置g.db为None，表示没有可用的数据库会话
        g.db = None

@app.teardown_request
def teardown_request(exception=None):
    """在每个请求结束后关闭数据库会话"""
    db = getattr(g, 'db', None)
    if db is not None:
        try:
            if exception:
                # 如果请求过程中发生异常，回滚事务
                try:
                    db.rollback()
                    logger.warning(f"请求处理异常，回滚数据库事务: {str(exception)}")
                except Exception as rollback_error:
                    logger.error(f"回滚数据库事务时出错: {str(rollback_error)}")
            # 关闭会话
            close_db_session(db)
            logger.debug("成功关闭请求级别的数据库会话")
        except Exception as e:
            logger.error(f"关闭数据库会话时出错: {str(e)}")

# 全局异常处理
@app.errorhandler(Exception)
def handle_exception(e):
    """全局异常处理器"""
    # 记录异常
    logger.error(f"全局异常: {str(e)}", exc_info=True)

    # 如果是SQLAlchemy相关异常，确保数据库会话被回滚
    db = getattr(g, 'db', None)
    if db is not None:
        try:
            db.rollback()
        except Exception as db_error:
            logger.error(f"异常处理中回滚数据库事务时出错: {str(db_error)}")

    # 返回错误响应
    return jsonify({
        'code': 0,
        'msg': f'服务器内部错误: {str(e)}'
    }), 500

# 处理Chrome DevTools的自动请求，避免404日志
@app.route('/.well-known/appspecific/com.chrome.devtools.json')
def chrome_devtools_json():
    """处理Chrome DevTools的自动请求，避免404日志"""
    return '', 204  # 返回空内容，状态码204 No Content

# 404错误处理器
@app.errorhandler(404)
def page_not_found(error):
    """处理404错误"""
    # 记录请求的URL和方法，但排除一些常见的无关请求
    request_path = request.path
    exclude_paths = [
        '/favicon.ico',
        '/robots.txt',
        '/sitemap.xml',
        '/.well-known/appspecific/com.chrome.devtools.json',
        '/apple-touch-icon',
        '/manifest.json'
    ]

    # 只记录真正的404错误，排除浏览器自动请求
    if not any(path in request_path for path in exclude_paths):
        logger.warning(f"404错误: {request.method} {request.path} | 参数: {dict(request.args)} | 来源: {request.remote_addr}")

    # 检查是否是API请求
    if request.path.startswith('/api/'):
        return jsonify({
            'code': 0,
            'msg': '请求的API端点不存在'
        }), 404

    # 网页请求返回友好的404页面
    current_year = datetime.now().year
    return render_template('404.html', current_year=current_year), 404

# 全局变量，存储Redis缓存实例
cache = None

# 初始化缓存 - 只在应用启动时执行一次
def init_redis_cache():
    global cache
    # 如果缓存已经初始化，直接返回
    if cache is not None:
        return
    try:
        if Config.REDIS_ENABLED:
            # 尝试连接Redis
            cache = RedisCache(Config.CACHE_EXPIRATION)
            # 测试连接
            cache.redis.ping()
            logger.info("Redis缓存初始化成功")
        else:
            cache = None
            logger.info("缓存功能已禁用")
    except Exception as e:
        # 如果Redis连接失败，禁用缓存
        logger.warning(f"Redis连接失败，缓存功能将被禁用: {str(e)}")
        cache = None
        Config.ENABLE_CACHE = False

# 应用启动时初始化Redis
init_redis_cache()

# Provider 初始化功能已移除 - 直接使用 config.json 配置

# 第三方代理池验证
def validate_proxy_pool():
    """验证第三方代理池配置"""
    try:
        from config.api_proxy_pool import get_api_proxy_pool
        proxy_pool = get_api_proxy_pool()

        active_proxies = proxy_pool.get_active_proxies()
        if not active_proxies:
            logging.warning("没有配置可用的第三方代理")
            return False

        logging.info(f"第三方代理池初始化成功，共 {len(active_proxies)} 个可用代理")
        for proxy in active_proxies:
            logging.info(f"  - {proxy.name}: {proxy.api_base} (优先级: {proxy.priority})")

        return True
    except Exception as e:
        logging.error(f"第三方代理池验证失败: {str(e)}")
        return False

# 验证第三方代理池
validate_proxy_pool()

# --- 简单内存IP限流装饰器 ---
ip_access = {}

def rate_limit(limit=60, period=60):
    def decorator(func):
        def wrapper(*args, **kwargs):
            ip = request.remote_addr
            now = int(time.time())
            window = now // period
            key = f'{func.__name__}:{ip}:{window}'
            count = ip_access.get(key, 0)
            if count >= limit:
                return jsonify({'code': 0, 'msg': '请求过于频繁，请稍后再试'}), 429
            ip_access[key] = count + 1
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

def verify_access_token(request):
    """验证访问令牌（如果配置了的话）"""
    if Config.ACCESS_TOKEN:
        token = request.headers.get('X-Access-Token') or request.args.get('token')
        if not token or token != Config.ACCESS_TOKEN:
            return False
    return True

@app.route('/api/search', methods=['GET', 'POST'])
@rate_limit(limit=60, period=60)
def search():
    """
    处理OCS发送的搜索请求，使用第三方AI API生成答案
    GET请求: 从URL参数获取问题
    POST请求: 从请求体获取问题

    参数:
        title: 问题内容
        type: 问题类型 (single-单选, multiple-多选, judgement-判断, completion-填空)
        options: 选项内容

    返回:
        成功: {'code': 1, 'question': '问题', 'answer': 'AI生成的答案'}
        失败: {'code': 0, 'msg': '错误信息'}
    """
    start_time = time.time()

    # 验证访问令牌（如果配置了的话）
    if not verify_access_token(request):
        return jsonify({
            'code': 0,
            'msg': '无效的访问令牌'
        }), 403

    try:
        # 根据请求方法获取问题内容
        if request.method == 'GET':
            question = request.args.get('title', '')
            question_type = request.args.get('type', '')
            options = request.args.get('options', '')
        else:  # POST
            content_type = request.headers.get('Content-Type', '')

            if 'application/json' in content_type:
                data = request.get_json()
                question = data.get('title', '')
                question_type = data.get('type', '')
                options = data.get('options', '')
            else:
                # 处理表单数据
                question = request.form.get('title', '')
                question_type = request.form.get('type', '')
                options = request.form.get('options', '')

        # 清理题目前缀
        from utils.question_cleaner import clean_question_prefix
        original_question = question
        question = clean_question_prefix(question)

        # 记录接收到的问题
        if original_question != question:
            logger.info(f"题目清理: 原始='{original_question[:50]}...' → 清理后='{question[:50]}...' (类型: {question_type})")
        else:
            logger.info(f"接收到问题: '{question[:50]}...' (类型: {question_type})")

        # 如果没有提供问题，返回错误
        if not question:
            logger.warning("未提供问题内容")
            return jsonify({
                'code': 0,
                'msg': '未提供问题内容'
            })

        # 检查缓存中是否有此问题的答案
        if Config.ENABLE_CACHE:
            cached_answer = cache.get(question, question_type, options)
            if cached_answer:
                logger.info(f"从缓存获取答案 (耗时: {time.time() - start_time:.2f}秒)")
                return jsonify(format_answer_for_ocs(question, cached_answer))

        # 代理池系统会自动选择最佳代理和模型，无需手动指定
        # 如果将来需要指定特定代理，可以使用 proxy_name 参数
        provider_id = None  # 使用默认代理池选择
        model = None        # 使用代理的默认模型

        # 构建基础提示
        base_prompt = parse_question_and_options(question, options, question_type)

        # 构建完整的提示，包含系统提示
        system_prompt = """你是一个专业的考试答题助手。请严格按照以下格式回答：

1. 单选题：只回答选项的具体内容，不要回答选项字母。例如：
   - 错误示例：C
   - 正确示例：说话轻、走路轻、操作轻、开关门轻

2. 多选题：回答多个选项的具体内容，用#号分隔，不要回答选项字母。例如：
   - 错误示例：A#C#D
   - 正确示例：中国#世界#地球

3. 判断题：只回答"正确"或"错误"

4. 填空题：直接给出答案内容

请务必回答选项的具体内容，而不是选项字母！"""

        # 将系统提示和用户提示合并
        full_prompt = f"{system_prompt}\n\n{base_prompt}"

        # 使用ModelService生成答案
        max_retries = 3
        retry_count = 0
        ai_answer = ""

        # 模型参数
        parameters = {
            "temperature": Config.TEMPERATURE,
            "max_tokens": Config.MAX_TOKENS
        }

        while retry_count < max_retries:
            try:
                # 使用SyncModelService生成答案，代理池会自动选择最佳代理
                response = SyncModelService.generate_response(
                    prompt=full_prompt,
                    provider_id=provider_id,  # None - 使用代理池默认选择
                    model=model,              # None - 使用代理的默认模型
                    parameters=parameters
                )

                # 如果成功获取答案
                if response and response.content:
                    ai_answer = response.content
                    logger.info(f"使用代理 {response.proxy_name} 的 {response.model} 模型生成答案成功")
                    break
                else:
                    logger.warning(f"生成答案失败，响应为空或无内容")

            except Exception as e:
                error_msg = f"生成答案异常: {str(e)}"
                logger.error(error_msg)

                # 代理池系统会自动进行故障转移，这里只记录错误
                logger.error(f"代理池调用失败: {error_msg}")
                # 代理池内部会尝试切换到其他可用代理

            # 增加重试计数
            retry_count += 1

        # 如果重试了最大次数仍未成功，返回错误
        if not ai_answer and retry_count >= max_retries:
            logger.error(f"达到最大重试次数 ({max_retries})，无法获取答案")
            return jsonify({
                'code': 0,
                'msg': f'请求失败，已尝试切换供应商并重试 {max_retries} 次'
            })

        # 处理答案格式
        processed_answer = extract_answer(ai_answer, question_type)
        logger.info(f"回答: {processed_answer}")

        # 保存到缓存
        if Config.ENABLE_CACHE:
            cache.set(question, processed_answer, question_type, options)

        # 校验必填字段
        def is_valid_record(question, question_type, options, answer):
            if not (question and question_type and answer and answer.strip()):
                return False
            qtype = (question_type or '').lower()
            if qtype in ('single', 'multiple'):
                return bool(options and options.strip())
            # 填空、判断题只需问题、类型、答案
            if qtype in ('completion', 'judgement'):
                return True
            # 其它类型可自定义
            return False

        if not is_valid_record(question, question_type, options, processed_answer):
            logger.info(f"题目字段不全，未写入数据库。题型: {question_type}, 问题: {question[:30]}, 选项: {options}, 答案: {processed_answer}")
            return jsonify(format_answer_for_ocs(question, processed_answer))

        # 查重：如已存在则更新，否则插入
        db_session = get_db_session()
        existing = db_session.query(QARecord).filter(
            QARecord.question == question,
            QARecord.type == question_type,
            QARecord.options == options
        ).first()
        if existing:
            existing.answer = processed_answer
            existing.created_at = datetime.now()
        else:
            qa_record = QARecord(
                question=question,
                type=question_type,
                options=options,
                answer=processed_answer,
                created_at=datetime.now()
            )
            db_session.add(qa_record)
        try:
            db_session.commit()
        finally:
            close_db_session(db_session)

        # 记录处理时间
        process_time = time.time() - start_time
        logger.info(f"问题处理完成 (耗时: {process_time:.2f}秒)")

        # 返回符合OCS格式的响应
        return jsonify(format_answer_for_ocs(question, processed_answer))

    except Exception as e:
        # 记录异常
        logger.error(f"处理问题时发生错误: {str(e)}", exc_info=True)

        # 捕获所有异常并返回错误信息
        return jsonify({
            'code': 0,
            'msg': f'发生错误: {str(e)}'
        })

@app.route('/api/health', methods=['GET'])
@rate_limit(limit=30, period=60)
def health_check():
    """健康检查接口"""
    try:
        from config.api_proxy_pool import get_api_proxy_pool
        from services.failover_manager import get_failover_manager

        # 获取代理池状态
        proxy_pool = get_api_proxy_pool()
        active_proxies = proxy_pool.get_active_proxies()

        # 获取故障转移状态
        failover_manager = get_failover_manager()

        # 构建健康状态响应
        health_status = {
            'status': 'ok',
            'message': 'AI题库服务运行正常',
            'version': '2.0.0',
            'timestamp': datetime.now().isoformat(),
            'cache_enabled': Config.ENABLE_CACHE,
            'proxy_pool': {
                'total_proxies': len(Config.THIRD_PARTY_APIS),
                'active_proxies': len(active_proxies),
                'proxy_names': [proxy.name for proxy in active_proxies],
                'failover_enabled': failover_manager.is_enabled()
            },
            'database': {
                'connected': True,  # 简化检查，实际可以添加数据库连接测试
                'type': Config.DB_TYPE
            }
        }

        # 如果没有可用代理，标记为警告状态
        if not active_proxies:
            health_status['status'] = 'warning'
            health_status['message'] = 'AI题库服务运行正常，但没有可用的代理'

        return jsonify(health_status)

    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'健康检查失败: {str(e)}',
            'version': '2.0.0',
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/health/detailed', methods=['GET'])
@rate_limit(limit=10, period=60)
def detailed_health_check():
    """详细健康检查接口"""
    try:
        from config.api_proxy_pool import get_api_proxy_pool
        from services.failover_manager import get_failover_manager

        # 获取代理池状态
        proxy_pool = get_api_proxy_pool()
        all_proxies = proxy_pool.proxies
        active_proxies = proxy_pool.get_active_proxies()

        # 获取故障转移管理器
        failover_manager = get_failover_manager()

        # 构建详细的代理状态
        proxy_details = []
        for proxy in all_proxies:
            health_status = failover_manager.get_proxy_health_status(proxy.name)
            proxy_info = {
                'name': proxy.name,
                'api_base': proxy.api_base,
                'is_active': proxy.is_active,
                'priority': proxy.priority,
                'model_count': len(proxy.models),
                'api_key_count': len(proxy.api_keys),
                'current_model': proxy.model,
                'health': health_status
            }
            proxy_details.append(proxy_info)

        # 系统整体状态
        overall_status = 'healthy'
        if not active_proxies:
            overall_status = 'critical'
        elif len(active_proxies) < len(all_proxies) * 0.5:
            overall_status = 'degraded'

        return jsonify({
            'status': overall_status,
            'timestamp': datetime.now().isoformat(),
            'version': '2.0.0',
            'system': {
                'cache_enabled': Config.ENABLE_CACHE,
                'record_enabled': Config.ENABLE_RECORD,
                'database_type': Config.DB_TYPE,
                'failover_enabled': failover_manager.is_enabled()
            },
            'proxy_pool': {
                'total_proxies': len(all_proxies),
                'active_proxies': len(active_proxies),
                'healthy_proxies': len([p for p in all_proxies if failover_manager.is_proxy_healthy(p.name)]),
                'details': proxy_details
            },
            'recommendations': _get_health_recommendations(proxy_details, failover_manager)
        })

    except Exception as e:
        logger.error(f"详细健康检查失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'详细健康检查失败: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 500

def _get_health_recommendations(proxy_details, failover_manager):
    """生成健康状态建议"""
    recommendations = []

    # 检查不健康的代理
    unhealthy_proxies = [p for p in proxy_details if p['health']['status'] == 'unhealthy']
    if unhealthy_proxies:
        recommendations.append({
            'type': 'warning',
            'message': f'有 {len(unhealthy_proxies)} 个代理处于不健康状态',
            'action': '检查代理配置和API密钥有效性'
        })

    # 检查代理数量
    active_count = len([p for p in proxy_details if p['is_active']])
    if active_count < 2:
        recommendations.append({
            'type': 'warning',
            'message': '建议配置至少2个代理以确保高可用性',
            'action': '添加更多第三方代理配置'
        })

    # 检查故障转移状态
    if not failover_manager.is_enabled():
        recommendations.append({
            'type': 'info',
            'message': '自动故障转移已禁用',
            'action': '考虑启用自动故障转移以提高系统可靠性'
        })

    # 检查API密钥数量
    low_key_proxies = [p for p in proxy_details if p['api_key_count'] < 2]
    if low_key_proxies:
        recommendations.append({
            'type': 'info',
            'message': f'有 {len(low_key_proxies)} 个代理的API密钥数量较少',
            'action': '考虑为每个代理配置多个API密钥以提高稳定性'
        })

    return recommendations

@app.route('/api/cache/clear', methods=['POST'])
@rate_limit(limit=1, period=60)
def clear_cache():
    """清理缓存"""
    # 验证访问令牌
    if not verify_access_token(request):
        return jsonify({
            'success': False,
            'message': '无效的访问令牌'
        }), 403

    # 如果缓存未启用，返回错误
    if not Config.ENABLE_CACHE or cache is None:
        return jsonify({
            'success': False,
            'message': '缓存功能未启用'
        })

    # 清除缓存
    cleared = cache.clear()

    return jsonify({
        'success': True,
        'message': f'缓存已清除，共{cleared}条记录'
    })

@app.route('/api/record/update', methods=['POST'])
@rate_limit(limit=5, period=60)
def update_record():
    """更新问答记录"""
    try:
        data = request.get_json()
        record_id = int(data.get('record_id', -1))
        # 获取数据库会话
        db_session = get_db_session()
        # 查询记录
        record = db_session.query(QARecord).filter(QARecord.id == record_id).first()
        if not record:
            return jsonify({
                'success': False,
                'message': '记录不存在'
            })
        # 检查是否有可更新字段（None或空字符串都视为未更新）
        updatable = False
        for field in ['question', 'type', 'options', 'answer']:
            if field in data and data[field] is not None and str(data[field]).strip() != '':
                updatable = True
                break
        if not updatable:
            # 记录无效更新请求
            app.logger.info(f"无效题目更新请求：仅传record_id={record_id}，无其它字段")
            return jsonify({
                'success': False,
                'message': '未提供任何可更新字段，未做任何更改'
            })
        # 更新记录
        if 'question' in data and data['question'] is not None and str(data['question']).strip() != '':
            record.question = data['question']
        if 'type' in data and data['type'] is not None and str(data['type']).strip() != '':
            record.type = data['type']
        if 'options' in data and data['options'] is not None and str(data['options']).strip() != '':
            record.options = data['options']
        if 'answer' in data and data['answer'] is not None and str(data['answer']).strip() != '':
            record.answer = data['answer']
        try:
            db_session.commit()
            # 如果启用了缓存，更新缓存
            if Config.ENABLE_CACHE:
                cache.delete(f'qa_{record_id}')
            return jsonify({
                'success': True,
                'message': '记录已更新'
            })
        finally:
            close_db_session(db_session)
    except Exception as e:
        app.logger.error(f"更新记录异常: {e}")
        return jsonify({
            'success': False,
            'message': f'更新失败: {e}'
        })

@app.route('/api/record/delete', methods=['POST'])
@rate_limit(limit=5, period=60)
def delete_record():
    """删除问答记录"""
    # 移除访问令牌校验
    try:
        data = request.get_json()
        record_id = int(data.get('record_id', -1))
        # 获取数据库会话
        db_session = get_db_session()
        # 查询记录
        record = db_session.query(QARecord).filter(QARecord.id == record_id).first()
        if not record:
            return jsonify({
                'success': False,
                'message': '记录不存在'
            })
        # 如果启用了缓存，删除缓存
        if Config.ENABLE_CACHE and cache is not None:
            try:
                cache.delete(record.question, record.type, record.options)
            except Exception as e:
                logger.warning(f"删除缓存时发生错误: {str(e)}")
        logger.info(f"删除记录 {record.id}: '{record.question[:30]}...'")
        db_session.delete(record)
        try:
            db_session.commit()
            return jsonify({
                'success': True,
                'message': '记录已删除'
            })
        finally:
            close_db_session(db_session)
    except Exception as e:
        logger.error(f"删除记录时发生错误: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'发生错误: {str(e)}'
        }), 500

# 用户认证装饰器
def login_required(view_func):
    @functools.wraps(view_func)
    def wrapped_view(*args, **kwargs):
        # 检查用户是否已登录
        if 'user_id' not in session:
            # 检查cookies中是否有会话ID
            session_id = request.cookies.get('session_id')
            if session_id:
                # 获取数据库会话
                db_session = get_db_session()
                # 验证会话
                user_id = UserSession.validate_session(db_session, session_id)
                if user_id:
                    # 将用户ID存入session
                    session['user_id'] = user_id
                    # 获取用户信息
                    user = get_user_by_id(db_session, user_id)
                    if user:
                        session['username'] = user.username
                        session['is_admin'] = user.is_admin
                    else:
                        return redirect(url_for('auth.login'))
                else:
                    return redirect(url_for('auth.login'))
            else:
                return redirect(url_for('auth.login'))
        return view_func(*args, **kwargs)
    return wrapped_view

# 管理员权限装饰器
def admin_required(view_func):
    @functools.wraps(view_func)
    def wrapped_view(*args, **kwargs):
        # 先验证登录
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))

        # 验证管理员权限
        if not session.get('is_admin', False):
            return render_template('error.html', error="您没有管理员权限访问此页面")

        return view_func(*args, **kwargs)
    return wrapped_view

# 首页
@app.route('/', methods=['GET'])
def index():
    """首页 - 显示Web界面"""
    current_year = datetime.now().year
    return render_template('index.html', current_year=current_year)

# 添加登录要求到管理页面
@app.route('/dashboard', methods=['GET'])
@login_required
@admin_required
def dashboard():
    """仪表盘 - 显示问答记录和系统状态"""
    current_year = datetime.now().year

    # 安全获取运行时间
    try:
        # 尝试使用全局start_time
        uptime_seconds = time.time() - globals().get('start_time', time.time())
    except Exception:
        # 如果出现任何问题，使用默认值
        uptime_seconds = 0

    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    uptime_str = f"{days}天{hours}小时{minutes}分钟"

    # 从数据库获取记录
    records = g.db.query(QARecord).order_by(QARecord.created_at.desc()).limit(100).all()
    records_data = [record.to_dict() for record in records]

    # 安全获取缓存大小
    cache_size = cache.size if (Config.ENABLE_CACHE and cache is not None) else 0

    # 获取当前使用的代理信息
    try:
        from config.api_proxy_pool import get_api_proxy_pool
        proxy_pool = get_api_proxy_pool()
        primary_proxy = proxy_pool.get_primary_proxy()
        current_model = primary_proxy.model if primary_proxy else "未配置代理"
        proxy_count = len(proxy_pool.get_active_proxies())
    except Exception:
        current_model = "代理池未初始化"
        proxy_count = 0

    return render_template(
        'dashboard.html',
        version="2.0.0",
        cache_enabled=Config.ENABLE_CACHE,
        cache_size=cache_size,
        model=current_model,
        proxy_count=proxy_count,
        uptime=uptime_str,
        records=records_data,
        current_year=current_year
    )

@app.route('/docs', methods=['GET'])
# @login_required  # 如果需要限制访问，取消此行注释
def docs():
    """API文档页面"""
    current_year = datetime.now().year
    return render_template('api_docs.html', current_year=current_year)

# Session设置功能已移除 - 不再需要通过session获取tokens

@app.route('/ai-search', methods=['GET'])
def ai_search_page():
    return render_template('ai_search.html')

@app.route('/logs', methods=['GET'])
def logs():
    # 读取日志内容（只取最后2000行，防止太大）
    log_file = os.path.join('logs', 'app.log')
    log_content = ""
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            log_content = ''.join(lines[-2000:])
    current_year = datetime.now().year
    return render_template('logs.html', log_content=log_content, version="1.1.0", current_year=current_year)

@app.route('/register', methods=['GET', 'POST'])
def register():
    # 禁止注册，显示提示信息
    return render_template('error.html', error='当前系统已关闭注册，如需账号请联系管理员。')

@app.route('/api/key_pool', methods=['GET'])
def key_pool():
    """
    获取多代理池密钥信息的API端点
    返回：
        - proxies: 代理列表，每个代理包含密钥信息
        - total_keys: 总密钥数
        - active_proxies: 激活的代理数
        - updated_at: 最后更新时间
    """
    try:
        from config.api_proxy_pool import get_api_proxy_pool
        from datetime import datetime
        import os

        # 获取代理池
        proxy_pool = get_api_proxy_pool()

        # 获取配置文件的最后修改时间
        try:
            mtime = os.path.getmtime('config.json')
            updated_at = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            logger.warning(f"获取配置文件修改时间失败: {str(e)}")
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 构建代理信息
        proxies_info = []
        total_keys = 0
        active_proxies = 0

        for proxy in proxy_pool.proxies:
            # 对密钥进行掩码处理
            keys_masked = [
                k[:8] + '****' + k[-4:] if len(k) > 12 else k
                for k in proxy.api_keys
            ]

            current_key_masked = ''
            if proxy.current_api_key:
                current_key_masked = (
                    proxy.current_api_key[:8] + '****' + proxy.current_api_key[-4:]
                    if len(proxy.current_api_key) > 12
                    else proxy.current_api_key
                )

            proxy_info = {
                'name': proxy.name,
                'api_base': proxy.api_base,
                'is_active': proxy.is_active,
                'priority': proxy.priority,
                'keys_count': len(proxy.api_keys),
                'keys': keys_masked,
                'current_key': current_key_masked,
                'models_count': len(proxy.models),
                'default_model': proxy.model
            }

            proxies_info.append(proxy_info)
            total_keys += len(proxy.api_keys)
            if proxy.is_active:
                active_proxies += 1

        return jsonify({
            'proxies': proxies_info,
            'total_keys': total_keys,
            'active_proxies': active_proxies,
            'total_proxies': len(proxy_pool.proxies),
            'updated_at': updated_at,
            'status': 'success'
        })

    except Exception as e:
        logger.error(f"获取代理池密钥信息失败: {str(e)}")
        from datetime import datetime
        return jsonify({
            'proxies': [],
            'total_keys': 0,
            'active_proxies': 0,
            'total_proxies': 0,
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'error',
            'message': f"获取代理池密钥信息失败: {str(e)}"
        }), 500

# 注册蓝图
app.register_blueprint(auth_bp)
app.register_blueprint(proxy_pool_bp)
app.register_blueprint(questions_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(logs_bp)
app.register_blueprint(proxy_management_bp)

# 注册图片代理蓝图
register_image_proxy_bp(app)

# 添加一个简单的测试端点，用于检查 API 是否可以正常响应
@app.route('/api/test', methods=['GET'])
def test_api():
    """测试 API 是否可以正常响应"""
    return jsonify({
        'success': True,
        'message': 'API 端点正常响应'
    })

# 添加清除所有缓存的API端点
@app.route('/api/cache/clear_all', methods=['POST'])
@rate_limit(limit=1, period=60)
def clear_all_cache():
    """清除所有缓存数据"""
    try:
        # 清除Redis缓存(如果启用)
        if cache is not None:
            cache.clear()
            logger.info("Redis缓存已清空")

        # 清除内存缓存（如果存在）
        try:
            from routes.questions import question_cache
            if question_cache is not None:
                question_cache.clear()
                logger.info("内存缓存已清空")
        except ImportError:
            logger.info("内存缓存模块不存在，跳过清除")

        # 清除代理池缓存（如果有的话）
        try:
            from config.api_proxy_pool import get_api_proxy_pool
            proxy_pool = get_api_proxy_pool()
            # 重新加载代理池配置
            proxy_pool.reload_config()
            logger.info("代理池配置已重新加载")
        except Exception as e:
            logger.warning(f"重新加载代理池配置失败: {str(e)}")

        return jsonify({"code": 1, "msg": "所有缓存已清空"})
    except Exception as e:
        logger.error(f"清空缓存失败: {str(e)}")
        return jsonify({"code": 0, "msg": f"清空缓存失败: {str(e)}"})

# 将当前请求的数据库会话注入到模板中
@app.context_processor
def inject_db():
    """将当前请求的数据库会话注入到模板中"""
    return {'db': getattr(g, 'db', None)}

@app.route('/api/proxy/performance-metrics', methods=['GET'])
def proxy_performance_metrics():
    """获取代理性能指标"""
    try:
        import random
        from datetime import datetime, timedelta

        # 模拟性能数据
        current_time = datetime.now()

        # 生成时间轴（最近12个时间点）
        timestamps = []
        requests = []
        for i in range(12):
            time_point = current_time - timedelta(minutes=i*5)
            timestamps.insert(0, time_point.strftime('%H:%M'))
            requests.insert(0, random.randint(10, 100))

        # 响应时间分布（模拟数据）
        response_distribution = {
            'under_100ms': random.randint(50, 80),
            'ms_100_500': random.randint(20, 40),
            'ms_500_1000': random.randint(5, 15),
            's_1_3': random.randint(1, 8),
            'over_3s': random.randint(0, 3)
        }

        return jsonify({
            'success': True,
            'total_requests': random.randint(1000, 5000),
            'avg_response_time': random.randint(200, 800),
            'success_rate': round(random.uniform(85, 99), 1),
            'request_timeline': {
                'timestamps': timestamps,
                'requests': requests
            },
            'response_distribution': response_distribution,
            'trends': {
                'requests': {
                    'direction': random.choice(['up', 'down', 'stable']),
                    'percentage': random.randint(1, 15)
                },
                'response_time': {
                    'direction': random.choice(['up', 'down', 'stable']),
                    'percentage': random.randint(1, 10)
                },
                'success_rate': {
                    'direction': random.choice(['up', 'down', 'stable']),
                    'percentage': random.randint(1, 5)
                }
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取性能指标失败: {str(e)}'
        }), 500

@app.route('/api/proxy/toggle-failover', methods=['POST'])
def toggle_proxy_failover():
    """切换自动故障切换状态"""
    try:
        from services.failover_manager import get_failover_manager

        data = request.get_json()
        enabled = data.get('enabled', False)

        failover_manager = get_failover_manager()

        if enabled:
            failover_manager.enable_failover()
        else:
            failover_manager.disable_failover()

        return jsonify({
            'success': True,
            'enabled': failover_manager.is_enabled(),
            'message': f'自动故障切换已{"启用" if enabled else "禁用"}'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'切换故障切换失败: {str(e)}'
        }), 500

@app.route('/api/proxy/failover-status', methods=['GET'])
def get_failover_status():
    """获取故障转移状态"""
    try:
        from services.failover_manager import get_failover_manager

        failover_manager = get_failover_manager()
        status = failover_manager.get_all_health_status()

        return jsonify({
            'success': True,
            'failover_status': status
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取故障转移状态失败: {str(e)}'
        }), 500

@app.route('/api/proxy/reset-health', methods=['POST'])
def reset_proxy_health():
    """重置代理健康状态"""
    try:
        from services.failover_manager import get_failover_manager

        data = request.get_json()
        proxy_name = data.get('proxy_name')

        failover_manager = get_failover_manager()

        if proxy_name:
            failover_manager.reset_proxy_health(proxy_name)
            message = f'已重置代理 {proxy_name} 的健康状态'
        else:
            failover_manager.reset_all_health()
            message = '已重置所有代理的健康状态'

        return jsonify({
            'success': True,
            'message': message
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'重置健康状态失败: {str(e)}'
        }), 500

@app.route('/api/dashboard/realtime', methods=['GET'])
def dashboard_realtime():
    """获取仪表盘实时数据"""
    try:
        import random
        from datetime import datetime, timedelta

        # 模拟实时数据
        return jsonify({
            'success': True,
            'today_questions': random.randint(100, 500),
            'avg_response_time': random.randint(200, 800),
            'success_rate': round(random.uniform(85, 99), 1),
            'active_users': random.randint(10, 50),
            'type_counts': {
                'single': random.randint(20, 100),
                'multiple': random.randint(10, 50),
                'judgement': random.randint(15, 60),
                'completion': random.randint(25, 80)
            },
            'proxy_status': {
                'healthy': random.choice([True, False]),
                'total_proxies': random.randint(2, 5),
                'active_proxies': random.randint(1, 3)
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取实时数据失败: {str(e)}'
        }), 500

# 定时任务已移除 - 不再需要自动同步API Key

if __name__ == '__main__':
    # 禁用Flask自动加载.env文件
    import os
    os.environ["FLASK_SKIP_DOTENV"] = "1"

    # 启动代理健康检查定时器
    try:
        from routes.proxy_management import start_health_check_timer
        start_health_check_timer()
    except Exception as e:
        logger.error(f"启动健康检查定时器失败: {str(e)}")

    # 开启应用
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
