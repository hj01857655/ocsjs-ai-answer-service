# -*- coding: utf-8 -*-
"""
EduBrain AI - 智能题库系统
基于 OpenAI API 的智能题库服务，提供兼容 OCS 接口的智能答题功能
作者：Lynn
版本：1.1.0
"""

import os
import json
import time
import logging
from datetime import datetime
import functools
import random
import shutil

from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from config import Config
from utils import format_answer_for_ocs, parse_question_and_options, extract_answer
from models import QARecord, UserSession, get_db_session, close_db_session, get_user_by_id
from services import RedisCache
from services import key_switcher
from config.model_providers import provider_manager, load_providers_from_file, initialize_default_providers, save_providers_to_file
from services.model_service import SyncModelService
from routes.auth import auth_bp
from routes.token import token_bp
from routes.questions import questions_bp
from routes.settings import settings_bp
from routes.logs import logs_bp
from routes.image_proxy import register_image_proxy_bp
from routes.provider import provider_bp
from services import sync_tokens_to_config
from apscheduler.schedulers.background import BackgroundScheduler

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

# 404错误处理器
@app.errorhandler(404)
def page_not_found(e):
    """处理404错误"""
    # 记录请求的URL和方法
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

# 初始化模型供应商配置
def initialize_model_providers():
    # 检查模型供应商配置文件是否存在
    if os.path.exists(Config.MODEL_PROVIDERS_FILE):
        # 加载现有配置
        logging.info(f"从文件加载模型供应商配置: {Config.MODEL_PROVIDERS_FILE}")
        load_providers_from_file(Config.MODEL_PROVIDERS_FILE)
    else:
        # 创建默认配置
        logging.info("创建默认模型供应商配置")
        initialize_default_providers()
        
        # 检查配置目录是否存在
        config_dir = os.path.dirname(Config.MODEL_PROVIDERS_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        # 保存默认配置
        save_providers_to_file(Config.MODEL_PROVIDERS_FILE)
        
        # 如果有示例文件，复制一份作为参考
        example_file = f"{Config.MODEL_PROVIDERS_FILE}.example"
        if os.path.exists(example_file):
            target_example = f"{Config.MODEL_PROVIDERS_FILE}.example.reference"
            shutil.copy2(example_file, target_example)
            logging.info(f"已复制示例配置文件到: {target_example}")
    
    # 检查是否有可用的供应商
    active_providers = provider_manager.get_active_providers()
    if not active_providers:
        logging.warning("没有找到可用的模型供应商，将使用默认配置")
        initialize_default_providers()
    else:
        logging.info(f"找到 {len(active_providers)} 个可用的模型供应商")
        for provider in active_providers:
            logging.info(f"  - {provider.name} ({provider.provider_id}): {provider.default_model}")

# 验证OpenAI API密钥
def validate_openai_key():
    try:
        if Config.OPENAI_API_KEY:
            import httpx
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {Config.OPENAI_API_KEY}"
            }
            payload = {
                "model": Config.OPENAI_MODEL,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5
            }
            with httpx.Client(verify=False) as client:
                response = client.post(
                    f"{Config.OPENAI_API_BASE}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=10.0
                )
                response.raise_for_status()
                logging.info(f"OpenAI API密钥验证成功")
                return True
        else:
            logging.warning("OpenAI API密钥未配置")
            return False
    except Exception as e:
        logging.error(f"OpenAI API密钥验证失败: {str(e)}")
        return False

# 初始化模型供应商配置
initialize_model_providers()

# 验证OpenAI API密钥
validate_openai_key()

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
    处理OCS发送的搜索请求，使用OpenAI API生成答案
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
        
        # 记录接收到的问题
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
        
        # 获取模型参数，优先用前端传入的参数，否则用默认
        provider_id = request.json.get('provider_id') if request.is_json else request.args.get('provider_id')
        model = request.json.get('model') if request.is_json else request.args.get('model')
        
        # 构建基础提示
        base_prompt = parse_question_and_options(question, options, question_type)

        # 构建完整的提示，包含系统提示
        system_prompt = "你是一个专业的考试答题助手。请直接回答答案，不要解释。选择题只回答选项的内容(如：地球)；多选题用#号分隔答案,只回答选项的内容(如中国#世界#地球)；判断题只回答: 正确/对/true/√ 或 错误/错/false/×；填空题直接给出答案。"

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
                # 使用SyncModelService生成答案
                response = SyncModelService.generate_response(
                    prompt=full_prompt,
                    provider_id=provider_id,  # 如果为None，则使用默认供应商
                    model=model,  # 如果为None，则使用供应商的默认模型
                    parameters=parameters
                )
                
                # 如果成功获取答案
                if response and response.get('content'):
                    ai_answer = response['content']
                    logger.info(f"使用 {response.get('provider_id')} 的 {response.get('model')} 模型生成答案成功")
                    break
                else:
                    logger.warning(f"生成答案失败，响应为空或无内容")
                    retry_count += 1
                    continue
                    
            except Exception as e:
                error_msg = f"生成答案异常: {str(e)}"
                logger.error(error_msg)
                
                # 如果是特定供应商或模型的错误，尝试切换到默认供应商
                if provider_id or model:
                    logger.info(f"尝试切换到默认供应商和模型")
                    provider_id = None
                    model = None
                    retry_count += 1
                    continue
                
                # 如果已经是默认供应商，返回错误
                return jsonify({
                    'code': 0,
                    'msg': error_msg
                })
            
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
    # 随机清除Token缓存 (5%概率)
    if random.random() < 0.05:
        cache_cleared = key_switcher.clear_token_cache()
        if cache_cleared > 0:
            logger.info(f"健康检查时随机清除了Token缓存 ({cache_cleared}条记录)")
            
    return jsonify({
        'status': 'ok',
        'message': 'AI题库服务运行正常',
        'version': '1.0.0',
        'cache_enabled': Config.ENABLE_CACHE,
        'model': Config.OPENAI_MODEL
    })

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
    uptime_seconds = time.time() - start_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    uptime_str = f"{days}天{hours}小时{minutes}分钟"
    
    # 从数据库获取记录
    records = g.db.query(QARecord).order_by(QARecord.created_at.desc()).limit(100).all()
    records_data = [record.to_dict() for record in records]
    
    # 安全获取缓存大小
    cache_size = cache.size if (Config.ENABLE_CACHE and cache is not None) else 0
    
    return render_template(
        'dashboard.html',
        version="1.1.0",
        cache_enabled=Config.ENABLE_CACHE,
        cache_size=cache_size,
        model=Config.OPENAI_MODEL,
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

@app.route('/session/set', methods=['POST'])
def set_session_ajax():
    session_value = request.json.get('session_value', '').strip()
    if session_value:
        session['veloera_session'] = session_value
        
        # 更新 config.json 中的 session
        try:
            # 读取当前配置
            with open('config.json', 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 更新 session
            if 'openai' not in config_data:
                config_data['openai'] = {}
            config_data['openai']['session'] = session_value
            
            # 写回配置文件
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            
            # 立即同步 tokens 到 config.json
            from services.token_sync import sync_tokens_to_config
            sync_tokens_to_config()
            
            logger.info("Session 已保存并同步到 config.json")
            return jsonify({"success": True, "message": "Session 已保存并同步到配置文件"})
        except Exception as e:
            logger.error(f"保存 Session 到配置文件失败: {str(e)}")
            return jsonify({"success": False, "message": f"Session 已保存但同步失败: {str(e)}"})
    return jsonify({"success": False, "message": "请输入有效的 session 值"})

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
    获取密钥池信息的API端点
    返回：
        - count: 密钥总数
        - current: 当前主密钥（部分掩码）
        - keys: 所有密钥列表（部分掩码）
        - updated_at: 最后更新时间
    """
    try:
        # 读取配置文件
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        # 获取密钥列表和当前主密钥
        keys = config.get('openai', {}).get('api_keys', [])
        current = config.get('openai', {}).get('api_key', '')
        
        # 对密钥进行掩码处理，保留前8位和后4位
        keys_masked = [k[:8] + '****' + k[-4:] if len(k) > 12 else k for k in keys]
        current_masked = current[:8] + '****' + current[-4:] if len(current) > 12 else current
        
        # 获取配置文件的最后修改时间
        import os
        from datetime import datetime
        try:
            mtime = os.path.getmtime('config.json')
            updated_at = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            logger.warning(f"获取配置文件修改时间失败: {str(e)}")
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
        return jsonify({
            'count': len(keys),
            'keys': keys_masked,
            'current': current_masked,
            'updated_at': updated_at,
            'status': 'success'
        })
        
    except Exception as e:
        logger.error(f"获取密钥池信息失败: {str(e)}")
        return jsonify({
            'count': 0,
            'keys': [],
            'current': '',
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'error',
            'message': f"获取密钥池信息失败: {str(e)}"
        }), 500

# 注册Blueprint# 注册蓝图
app.register_blueprint(auth_bp)
app.register_blueprint(token_bp)
app.register_blueprint(questions_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(logs_bp)
from routes.provider import provider_bp
app.register_blueprint(provider_bp)

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
def clear_all_cache():
    """清除所有缓存数据"""
    try:
        # 清除Redis缓存(如果启用)
        if cache is not None:
            cache.clear()
            logger.info("Redis缓存已清空")
        
        # 清除内存缓存
        from routes.questions import question_cache
        if question_cache is not None:
            question_cache.clear()
            logger.info("内存缓存已清空")
            
        # 清除token缓存
        from services.key_switcher import clear_token_cache
        cleared_count = clear_token_cache()
        logger.info(f"Token缓存已清空，共{cleared_count}条")
        
        return jsonify({"code": 1, "msg": "所有缓存已清空"})
    except Exception as e:
        logger.error(f"清空缓存失败: {str(e)}")
        return jsonify({"code": 0, "msg": f"清空缓存失败: {str(e)}"})

# 将当前请求的数据库会话注入到模板中
@app.context_processor
def inject_db():
    """将当前请求的数据库会话注入到模板中"""
    return {'db': getattr(g, 'db', None)}

# 启动定时任务，每小时自动同步API Key
scheduler = BackgroundScheduler()
scheduler.add_job(sync_tokens_to_config, 'interval', hours=1, id='token_sync_job', replace_existing=True)
scheduler.start()

if __name__ == '__main__':
    # 记录应用启动时间
    start_time = time.time()
    
    # 禁用Flask自动加载.env文件
    import os
    os.environ["FLASK_SKIP_DOTENV"] = "1"
    
    # 开启应用
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
