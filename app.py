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
import openai
from datetime import datetime
import functools
import httpx
import requests

from flask import Flask, request, jsonify, render_template, redirect, url_for, session, make_response
from flask_cors import CORS
from config import Config
from utils import format_answer_for_ocs, parse_question_and_options, extract_answer
from models import QARecord, UserSession, get_db_session, authenticate_user, create_user, get_user_by_id
from cache import RedisCache
from logger import Logger

# 配置日志 - 只在控制台显示ERROR级别日志
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)
console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_format)

# 文件日志处理器保持原来的配置
if not os.path.exists('logs'):
    os.makedirs('logs')
file_handler = logging.FileHandler(os.path.join('logs', 'app.log'), encoding='utf-8')
file_handler.setLevel(getattr(logging, Config.LOG_LEVEL))
file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_format)

# 配置根日志记录器
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[console_handler, file_handler]
)

# 禁用Flask自带的werkzeug日志记录器，仅显示ERROR级别
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)

logger = logging.getLogger('ai_answer_service')

# 初始化应用
app = Flask(__name__)
CORS(app)  # 启用CORS支持

# 设置应用密钥，用于会话加密
app.secret_key = Config.SECRET_KEY if hasattr(Config, 'SECRET_KEY') else os.urandom(24)

# 禁用Flask内置日志，仅保留错误级别
app.logger.setLevel(logging.ERROR)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# 初始化数据库会话
db = get_db_session()

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

# 验证OpenAI API密钥
if not Config.OPENAI_API_KEY:
    logger.critical("未设置OpenAI API密钥，请在config.json文件中配置openai.api_key")
    raise ValueError("请设置OpenAI API密钥")

# 确保API基础URL格式正确
api_base = Config.OPENAI_API_BASE
if not api_base.endswith('/'):
    api_base += '/'
if '//' in api_base[8:]:  # 避免URL中有重复的斜杠
    api_base = api_base.replace('/v1/', '/v1')

# 初始化OpenAI客户端
try:
    client = openai.OpenAI(
        api_key=Config.OPENAI_API_KEY,
        base_url=api_base,
        http_client=httpx.Client(
            verify=False,  # 禁用SSL验证
            timeout=60.0   # 增加超时时间
        )
    )
    logger.info(f"OpenAI客户端初始化成功，API基础URL: {api_base}")
except Exception as e:
    logger.critical(f"OpenAI客户端初始化失败: {str(e)}")
    raise

# 应用启动时间
start_time = time.time()

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
        
        # 构建发送给OpenAI的提示
        prompt = parse_question_and_options(question, options, question_type)
        
        # --- 优化：严格适配代理API的fetch请求格式和流式响应 ---
        headers = {
            "accept": "application/json",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "authorization": f"Bearer {Config.OPENAI_API_KEY}",
            "content-type": "application/json",
            # 以下头部可选，模拟浏览器更真实
            # "priority": "u=1, i",
            # "sec-ch-ua": '"Chromium";v="136", "Microsoft Edge";v="136", "Not.A/Brand";v="99"',
            # "sec-ch-ua-mobile": "?0",
            # "sec-ch-ua-platform": '"Windows"',
            # "sec-fetch-dest": "empty",
            # "sec-fetch-mode": "cors",
            # "sec-fetch-site": "cross-site",
            # "Referer": "https://app.nextchat.dev/",
            # "Referrer-Policy": "strict-origin-when-cross-origin"
        }
        # 构造body，严格仿照fetch格式
        data = {
            "messages": [
                {"role": "system", "content": "你是一个专业的考试答题助手。请直接回答答案，不要解释。选择题只回答选项的内容(如：地球)；多选题用#号分隔答案,只回答选项的内容(如中国#世界#地球)；判断题只回答: 正确/对/true/√ 或 错误/错/false/×；填空题直接给出答案。"},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "model": Config.OPENAI_MODEL,
            "temperature": Config.TEMPERATURE,
            "presence_penalty": 0,
            "frequency_penalty": 0,
            "top_p": 1,
            "max_tokens": Config.MAX_TOKENS
        }
        ai_answer = ""
        try:
            resp = httpx.post(
                f"{Config.OPENAI_API_BASE.rstrip('/')}/chat/completions",
                headers=headers,
                json=data,
                timeout=60.0,
                verify=False
            )
            if resp.status_code == 200:
                # 用UTF-8解码，兼容流式响应
                for line in resp.text.strip().split('\n'):
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            json_str = line[len("data: "):]
                            data = json.loads(json_str)
                            content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if content:
                                ai_answer += content
                        except Exception as e:
                            logger.warning(f"解析流式响应行失败: {str(e)}")
            else:
                logger.error(f"代理API请求失败: {resp.status_code} - {resp.text}")
                return jsonify({
                    'code': 0,
                    'msg': f'代理API请求失败: {resp.status_code} - {resp.text}'
                })
        except Exception as e:
            logger.error(f"代理API请求异常: {str(e)}")
            return jsonify({
                'code': 0,
                'msg': f'代理API请求异常: {str(e)}'
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
        existing = db.query(QARecord).filter(
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
            db.add(qa_record)
        db.commit()
        
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
    """清除缓存接口"""
    # 验证访问令牌
    if not verify_access_token(request):
        return jsonify({
            'success': False,
            'message': '无效的访问令牌'
        }), 403
    
    if not Config.ENABLE_CACHE:
        return jsonify({
            'success': False,
            'message': '缓存未启用'
        })
    
    cleared = cache.clear()
    return jsonify({
        'success': True,
        'message': f'缓存已清除，共{cleared}条记录'
    })

@app.route('/api/stats', methods=['GET'])
@rate_limit(limit=30, period=60)
def get_stats():
    """获取服务统计信息"""
    # 验证访问令牌
    if not verify_access_token(request):
        return jsonify({
            'success': False,
            'message': '无效的访问令牌'
        }), 403
    
    # 查询记录总数
    records_count = db.query(QARecord).count()
    
    stats = {
        'version': '1.0.0',
        'uptime': time.time() - start_time,
        'model': Config.OPENAI_MODEL,
        'cache_enabled': Config.ENABLE_CACHE,
        'cache_size': cache.size if Config.ENABLE_CACHE else 0,
        'qa_records_count': records_count
    }
    
    return jsonify(stats)

@app.route('/api/record/update', methods=['POST'])
@rate_limit(limit=5, period=60)
def update_record():
    """更新问答记录"""
    # 验证访问令牌
    if not verify_access_token(request):
        return jsonify({
            'success': False,
            'message': '无效的访问令牌'
        }), 403
    
    try:
        data = request.get_json()
        record_id = int(data.get('record_id', -1))
        
        # 查询记录
        record = db.query(QARecord).filter(QARecord.id == record_id).first()
        
        if not record:
            return jsonify({
                'success': False,
                'message': '记录不存在'
            })
        
        # 更新记录
        record.question = data.get('question', record.question)
        record.type = data.get('type', record.type)
        record.options = data.get('options', record.options)
        record.answer = data.get('answer', record.answer)
        
        # 提交更新
        db.commit()
        
        # 如果启用了缓存，更新缓存
        if Config.ENABLE_CACHE:
            # 先删除旧缓存
            cache.delete(record.question, record.type, record.options)
            # 添加新缓存
            cache.set(record.question, record.answer, record.type, record.options)
        
        logger.info(f"更新记录 {record.id}: '{record.question[:30]}...'")
        
        return jsonify({
            'success': True,
            'message': '记录已更新'
        })
    
    except Exception as e:
        logger.error(f"更新记录时发生错误: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'发生错误: {str(e)}'
        })

@app.route('/api/record/delete', methods=['POST'])
@rate_limit(limit=5, period=60)
def delete_record():
    """删除问答记录"""
    # 验证访问令牌
    if not verify_access_token(request):
        return jsonify({
            'success': False,
            'message': '无效的访问令牌'
        }), 403
    
    try:
        data = request.get_json()
        record_id = int(data.get('record_id', -1))
        
        # 查询记录
        record = db.query(QARecord).filter(QARecord.id == record_id).first()
        
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
        
        # 记录日志
        logger.info(f"删除记录 {record.id}: '{record.question[:30]}...'")
        
        # 删除记录
        db.delete(record)
        db.commit()
        
        return jsonify({
            'success': True,
            'message': '记录已删除'
        })
    
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
                # 验证会话
                user_id = UserSession.validate_session(db, session_id)
                if user_id:
                    # 将用户ID存入session
                    session['user_id'] = user_id
                    # 获取用户信息
                    user = get_user_by_id(db, user_id)
                    if user:
                        session['username'] = user.username
                        session['is_admin'] = user.is_admin
                    else:
                        return redirect(url_for('login'))
                else:
                    return redirect(url_for('login'))
            else:
                return redirect(url_for('login'))
        return view_func(*args, **kwargs)
    return wrapped_view

# 管理员权限装饰器
def admin_required(view_func):
    @functools.wraps(view_func)
    def wrapped_view(*args, **kwargs):
        # 先验证登录
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        # 验证管理员权限
        if not session.get('is_admin', False):
            return render_template('error.html', error="您没有管理员权限访问此页面")
        
        return view_func(*args, **kwargs)
    return wrapped_view

# 注册页面
@app.route('/register', methods=['GET', 'POST'])
@rate_limit(limit=5, period=60)
def register():
    """用户注册页面"""
    current_year = datetime.now().year
    # 如果用户已经登录，则重定向到首页
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    error = None
    if request.method == 'POST':
        # 获取表单数据
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        email = request.form.get('email', '').strip() or None
        
        # 基本验证
        if not username or not password:
            error = "用户名和密码不能为空"
        elif len(username) < 3:
            error = "用户名长度不能少于3个字符"
        elif len(password) < 6:
            error = "密码长度不能少于6个字符"
        elif password != confirm_password:
            error = "两次输入的密码不一致"
        else:
            # 创建用户
            user, err = create_user(db, username, password, email)
            if user:
                # 设置登录状态
                session['user_id'] = user.id
                session['username'] = user.username
                session['is_admin'] = user.is_admin
                
                # 创建持久会话
                session_id = UserSession.create_session(
                    db, 
                    user.id, 
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string
                )
                
                # 更新用户最后登录时间
                user.last_login = datetime.now()
                db.commit()
                
                # 设置cookie
                response = make_response(redirect(url_for('index')))
                response.set_cookie('session_id', session_id, max_age=30*24*60*60, httponly=True)
                
                return response
            else:
                error = err
    
    return render_template('register.html', error=error, current_year=current_year)

# 登录页面
@app.route('/login', methods=['GET', 'POST'])
@rate_limit(limit=5, period=60)
def login():
    """用户登录页面"""
    current_year = datetime.now().year
    # 如果用户已经登录，则重定向到首页
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    error = None
    if request.method == 'POST':
        # 获取表单数据
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', '') == 'on'
        
        # 认证用户
        user = authenticate_user(db, username, password)
        if user:
            # 设置登录状态
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            
            # 如果选择了"记住我"，则创建持久会话
            if remember:
                session_id = UserSession.create_session(
                    db, 
                    user.id, 
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string
                )
                
                # 更新用户最后登录时间
                user.last_login = datetime.now()
                db.commit()
                
                # 设置cookie
                response = make_response(redirect(url_for('index')))
                response.set_cookie('session_id', session_id, max_age=30*24*60*60, httponly=True)
                
                return response
            
            # 更新用户最后登录时间
            user.last_login = datetime.now()
            db.commit()
            
            return redirect(url_for('index'))
        else:
            error = "用户名或密码错误"
    
    return render_template('login.html', error=error, current_year=current_year)

# 退出登录
@app.route('/logout')
def logout():
    """退出登录"""
    # 删除会话
    session_id = request.cookies.get('session_id')
    if session_id:
        UserSession.delete_session(db, session_id)
    
    # 清除会话数据
    session.clear()
    
    # 清除cookie
    response = make_response(redirect(url_for('login')))
    response.delete_cookie('session_id')
    
    return response

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
    records = db.query(QARecord).order_by(QARecord.created_at.desc()).limit(100).all()
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

@app.route('/logs', methods=['GET'])
@login_required
@admin_required
def logs_panel():
    """日志面板 - 显示系统日志"""
    current_year = datetime.now().year
    # 获取最近的日志
    log_content = Logger.get_latest_logs(max_lines=1000)
    
    # 获取系统状态信息
    uptime_seconds = time.time() - start_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    uptime_str = f"{days}天{hours}小时{minutes}分钟"
    
    return render_template(
        'logs.html',
        version="1.1.0",
        log_content=log_content,
        model=Config.OPENAI_MODEL,
        uptime=uptime_str,
        current_year=current_year
    )

@app.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    """配置页面 - 允许用户修改系统配置"""
    current_year = datetime.now().year
    # 获取当前配置
    current_config = {
        # 数据库配置
        'DB_TYPE': Config.DB_TYPE,
        'DB_HOST': Config.DB_HOST,
        'DB_PORT': Config.DB_PORT,
        'DB_USER': Config.DB_USER,
        'DB_PASSWORD': Config.DB_PASSWORD,
        'DB_NAME': Config.DB_NAME,
        
        # Redis配置
        'REDIS_ENABLED': Config.REDIS_ENABLED,
        'REDIS_HOST': Config.REDIS_HOST,
        'REDIS_PORT': Config.REDIS_PORT,
        'REDIS_PASSWORD': Config.REDIS_PASSWORD,
        'REDIS_DB': Config.REDIS_DB,
        
        # 缓存配置
        'ENABLE_CACHE': Config.ENABLE_CACHE,
        'CACHE_EXPIRATION': Config.CACHE_EXPIRATION,
        
        # OpenAI配置
        'OPENAI_API_KEY': Config.OPENAI_API_KEY,
        'OPENAI_MODEL': Config.OPENAI_MODEL,
        'OPENAI_API_BASE': Config.OPENAI_API_BASE,
        'OPENAI_TEMPERATURE': Config.OPENAI_TEMPERATURE,
        'OPENAI_MAX_TOKENS': Config.OPENAI_MAX_TOKENS,
        
        # 其他配置
        'ENABLE_RECORD': Config.ENABLE_RECORD,
        'ACCESS_TOKEN': Config.ACCESS_TOKEN,
        'MAX_TOKENS': Config.MAX_TOKENS,
        'TEMPERATURE': Config.TEMPERATURE,
        'SSL_CERT_FILE': Config.SSL_CERT_FILE,
    }
    
    if request.method == 'POST':
        # 处理表单提交
        try:
            new_config = {
                # 缓存设置
                'ENABLE_CACHE': request.form.get('ENABLE_CACHE') == 'on',
                'CACHE_EXPIRATION': int(request.form.get('CACHE_EXPIRATION', Config.CACHE_EXPIRATION)),
                
                # OpenAI设置
                'OPENAI_API_KEY': request.form.get('OPENAI_API_KEY', Config.OPENAI_API_KEY),
                'OPENAI_MODEL': request.form.get('OPENAI_MODEL', Config.OPENAI_MODEL),
                'OPENAI_API_BASE': request.form.get('OPENAI_API_BASE', Config.OPENAI_API_BASE),
                'OPENAI_TEMPERATURE': float(request.form.get('OPENAI_TEMPERATURE', Config.OPENAI_TEMPERATURE)),
                'OPENAI_MAX_TOKENS': int(request.form.get('OPENAI_MAX_TOKENS', Config.OPENAI_MAX_TOKENS)),
                
                # 其他设置
                'ENABLE_RECORD': request.form.get('ENABLE_RECORD') == 'on',
                'ACCESS_TOKEN': request.form.get('ACCESS_TOKEN', Config.ACCESS_TOKEN),
                'MAX_TOKENS': Config.MAX_TOKENS,
                'TEMPERATURE': Config.TEMPERATURE,
                'SSL_CERT_FILE': Config.SSL_CERT_FILE
            }
            
            # 更新配置文件
            update_config(new_config)
            
            # 返回成功信息
            return render_template(
                'settings.html',
                success="配置已成功更新！",
                config=current_config,  # 重新加载当前配置
                current_year=current_year
            )
        except Exception as e:
            # 返回错误信息
            return render_template(
                'settings.html',
                error=f"更新配置失败: {str(e)}",
                config=current_config,
                current_year=current_year
            )
    
    # GET请求直接显示配置页面
    return render_template(
        'settings.html',
        config=current_config,
        current_year=current_year
    )

# 更新配置文件函数
def update_config(new_config):
    """更新系统配置"""
    # 更新运行时配置
    Config.ENABLE_CACHE = new_config.get('ENABLE_CACHE', Config.ENABLE_CACHE)
    Config.CACHE_EXPIRATION = new_config.get('CACHE_EXPIRATION', Config.CACHE_EXPIRATION)
    
    Config.ENABLE_RECORD = new_config.get('ENABLE_RECORD', Config.ENABLE_RECORD)
    
    Config.OPENAI_API_KEY = new_config.get('OPENAI_API_KEY', Config.OPENAI_API_KEY)
    Config.OPENAI_MODEL = new_config.get('OPENAI_MODEL', Config.OPENAI_MODEL)
    Config.OPENAI_API_BASE = new_config.get('OPENAI_API_BASE', Config.OPENAI_API_BASE)
    Config.OPENAI_TEMPERATURE = new_config.get('OPENAI_TEMPERATURE', Config.OPENAI_TEMPERATURE)
    Config.OPENAI_MAX_TOKENS = new_config.get('OPENAI_MAX_TOKENS', Config.OPENAI_MAX_TOKENS)
    
    Config.ACCESS_TOKEN = new_config.get('ACCESS_TOKEN', Config.ACCESS_TOKEN)
    
    # 更新配置文件
    config_data = {
        'service': {
            'host': Config.HOST,
            'port': Config.PORT,
            'debug': Config.DEBUG
        },
        'openai': {
            'api_key': Config.OPENAI_API_KEY,
            'model': Config.OPENAI_MODEL,
            'api_base': Config.OPENAI_API_BASE
        },
        'cache': {
            'enable': Config.ENABLE_CACHE,
            'expiration': Config.CACHE_EXPIRATION
        },
        'security': {
            'access_token': Config.ACCESS_TOKEN,
            'secret_key': Config.SECRET_KEY if hasattr(Config, 'SECRET_KEY') else os.urandom(24).hex()
        },
        'database': {
            'type': Config.DB_TYPE,
            'host': Config.DB_HOST,
            'port': Config.DB_PORT,
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD,
            'name': Config.DB_NAME
        },
        'redis': {
            'enabled': Config.REDIS_ENABLED,
            'host': Config.REDIS_HOST,
            'port': Config.REDIS_PORT,
            'password': Config.REDIS_PASSWORD,
            'db': Config.REDIS_DB
        },
        'record': {
            'enable': Config.ENABLE_RECORD
        }
    }
    
    # 保存到配置文件
    try:
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        logger.info("配置已保存到config.json文件")
        return True
    except Exception as e:
        logger.error(f"保存配置到config.json文件时发生错误: {str(e)}")
        raise e

@app.route('/docs', methods=['GET'])
# @login_required  # 如果需要限制访问，取消此行注释
def docs():
    """API文档页面"""
    current_year = datetime.now().year
    return render_template('api_docs.html', current_year=current_year)

@app.route('/questions', methods=['GET'])
@login_required
def questions():
    """题库管理页面"""
    current_year = datetime.now().year
    # 获取查询参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search_query = request.args.get('q', '')
    current_type = request.args.get('type', '')
    
    # 查询条件构建
    query = db.query(QARecord)
    
    # 按类型筛选
    if current_type:
        query = query.filter(QARecord.type == current_type)
    
    # 搜索条件
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            (QARecord.question.like(search_term)) | 
            (QARecord.answer.like(search_term))
        )
    
    # 计算总记录数和总页数
    total_records = query.count()
    total_pages = (total_records + per_page - 1) // per_page
    
    # 分页
    offset = (page - 1) * per_page
    records = query.order_by(QARecord.id.desc()).offset(offset).limit(per_page).all()
    
    # 获取各类型的数量统计
    type_counts = {
        'all': db.query(QARecord).count(),
        'single': db.query(QARecord).filter(QARecord.type == 'single').count(),
        'multiple': db.query(QARecord).filter(QARecord.type == 'multiple').count(),
        'judgement': db.query(QARecord).filter(QARecord.type == 'judgement').count(),
        'completion': db.query(QARecord).filter(QARecord.type == 'completion').count(),
    }
    
    return render_template(
        'questions.html',
        records=records,
        total_pages=total_pages,
        page=page,
        per_page=per_page,
        search_query=search_query,
        current_type=current_type,
        type_counts=type_counts,
        current_year=current_year
    )

@app.route('/api/questions/export', methods=['GET'])
@rate_limit(limit=5, period=60)
def export_questions():
    """导出题库数据为CSV文件"""
    # 验证访问令牌
    if not verify_access_token(request):
        return jsonify({
            'success': False,
            'message': '无效的访问令牌'
        }), 403
    
    try:
        # 获取查询参数
        question_type = request.args.get('type', '')
        search_query = request.args.get('q', '')
        # 构建查询
        query = db.query(QARecord)
        # 如果有搜索关键词
        if search_query:
            query = query.filter(QARecord.question.like(f'%{search_query}%') | 
                                QARecord.answer.like(f'%{search_query}%'))
        # 如果有类型筛选
        if question_type:
            query = query.filter(QARecord.type == question_type)
        # 获取所有符合条件的记录
        records = query.all()
        # 生成CSV内容
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        # 写入CSV标题行
        writer.writerow(['ID', '问题', '类型', '选项', '答案', '创建时间'])
        # 写入数据行
        for record in records:
            writer.writerow([
                record.id,
                record.question,
                record.type or '未知',
                record.options or '',
                record.answer,
                record.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        # 设置响应头
        from flask import Response
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment;filename=questions.csv'}
        )
        return response
    except Exception as e:
        logger.error(f"导出题库数据失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'导出题库数据失败: {str(e)}'
        }), 500

@app.route('/api/questions/import', methods=['POST'])
@rate_limit(limit=3, period=60)
def import_questions():
    """导入题库数据"""
    # 验证访问令牌
    if not verify_access_token(request):
        return jsonify({
            'success': False,
            'message': '无效的访问令牌'
        }), 403
    
    try:
        # 检查是否有文件上传
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'message': '没有上传文件'
            }), 400
        
        file = request.files['file']
        
        # 如果用户没有选择文件
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': '没有选择文件'
            }), 400
        
        # 检查文件扩展名
        if not file.filename.endswith('.csv'):
            return jsonify({
                'success': False,
                'message': '只支持导入CSV文件'
            }), 400
        
        # 解析CSV文件
        import csv
        import io
        stream = io.StringIO(file.stream.read().decode('utf-8'))
        reader = csv.reader(stream)
        
        # 跳过标题行
        next(reader)
        
        # 记录导入情况
        imported_count = 0
        error_count = 0
        
        # 处理每一行数据
        for row in reader:
            try:
                # 确保行数据完整
                if len(row) < 5:
                    error_count += 1
                    continue
                
                # 解析数据
                question = row[1].strip()
                question_type = row[2].strip() if row[2].strip() != '未知' else None
                options = row[3].strip()
                answer = row[4].strip()
                
                # 查重：如已存在则更新，否则插入
                existing = db.query(QARecord).filter(
                    QARecord.question == question,
                    QARecord.type == question_type,
                    QARecord.options == options
                ).first()
                if existing:
                    existing.answer = answer
                    existing.created_at = datetime.now()
                else:
                    qa_record = QARecord(
                        question=question,
                        type=question_type,
                        options=options,
                        answer=answer,
                        created_at=datetime.now()
                    )
                    db.add(qa_record)
                imported_count += 1
                
            except Exception as e:
                logger.error(f"导入数据行错误: {str(e)}", exc_info=True)
                error_count += 1
        
        # 提交所有更改
        db.commit()
        
        # 更新缓存
        if Config.ENABLE_CACHE and cache is not None:
            try:
                cache.clear()
                logger.info("导入数据后清除缓存")
            except Exception as e:
                logger.warning(f"清除缓存时发生错误: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': f'成功导入{imported_count}条记录，失败{error_count}条'
        })
    
    except Exception as e:
        logger.error(f"导入题库数据失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'导入题库数据失败: {str(e)}'
        }), 500

@app.route('/api/questions/batch-delete', methods=['POST'])
@rate_limit(limit=3, period=60)
def batch_delete_questions():
    """批量删除题库记录"""
    # 验证访问令牌
    if not verify_access_token(request):
        return jsonify({
            'success': False,
            'message': '无效的访问令牌'
        }), 403
    
    try:
        data = request.get_json()
        record_ids = data.get('record_ids', [])
        
        if not record_ids:
            return jsonify({
                'success': False,
                'message': '未提供要删除的记录ID'
            }), 400
        
        # 查询记录
        records = db.query(QARecord).filter(QARecord.id.in_(record_ids)).all()
        
        if not records:
            return jsonify({
                'success': False,
                'message': '未找到要删除的记录'
            }), 404
        
        # 如果启用了缓存，删除缓存
        if Config.ENABLE_CACHE and cache is not None:
            try:
                for record in records:
                    cache.delete(record.question, record.type, record.options)
            except Exception as e:
                logger.warning(f"删除缓存时发生错误: {str(e)}")
        
        # 记录日志
        logger.info(f"批量删除记录: {len(records)}条")
        
        # 删除记录
        for record in records:
            db.delete(record)
        
        db.commit()
        
        return jsonify({
            'success': True,
            'message': f'成功删除{len(records)}条记录'
        })
    
    except Exception as e:
        logger.error(f"批量删除记录时发生错误: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'发生错误: {str(e)}'
        }), 500

# 应用关闭时清理资源
@app.teardown_appcontext
def shutdown_session(exception=None):
    if 'db' in globals():
        db.close()

@app.route('/search', methods=['GET'])
def search_page():
    """公开题目搜索页面 - 不需要登录即可访问"""
    current_year = datetime.now().year
    # 获取查询参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search_query = request.args.get('q', '')
    current_type = request.args.get('type', '')
    
    # 查询条件构建
    query = db.query(QARecord)
    
    # 按类型筛选
    if current_type:
        query = query.filter(QARecord.type == current_type)
    
    # 搜索条件
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            (QARecord.question.like(search_term)) | 
            (QARecord.answer.like(search_term))
        )
    
    # 计算总记录数和总页数
    total_records = query.count()
    total_pages = (total_records + per_page - 1) // per_page
    
    # 分页
    offset = (page - 1) * per_page
    records = query.order_by(QARecord.id.desc()).offset(offset).limit(per_page).all()
    
    # 转换记录为字典
    records_data = [record.to_dict() for record in records]
    
    return render_template(
        'search.html',
        records=records_data,
        total_pages=total_pages,
        page=page,
        per_page=per_page,
        search_query=search_query,
        current_type=current_type,
        current_year=current_year
    )

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    headers = {
        "accept": "application/json, text/plain, */*",
        "veloera-user": "84",  # TODO: 替换为你的用户ID
        "cookie": "session=MTc0ODA4MjQ1NXxEWDhFQVFMX2dBQUJFQUVRQUFEX2xQLUFBQVVHYzNSeWFXNW5EQVFBQW1sa0EybHVkQVFEQVAtb0JuTjBjbWx1Wnd3S0FBaDFjMlZ5Ym1GdFpRWnpkSEpwYm1jTURBQUtiR2x1ZFhoa2IxODROQVp6ZEhKcGJtY01CZ0FFY205c1pRTnBiblFFQWdBQ0JuTjBjbWx1Wnd3SUFBWnpkR0YwZFhNRGFXNTBCQUlBQWdaemRISnBibWNNQndBRlozSnZkWEFHYzNSeWFXNW5EQWtBQjJSbFptRjFiSFE9fDaCcWAZ3FKaS4cu6oOUoD3U9iHo3U3hGRJ3wSg5AJdK"  # TODO: 替换为你的session
    }
    try:
        resp = httpx.get("https://veloera.wei.bi/api/token/?p=0&size=20", headers=headers, timeout=10.0, verify=Config.SSL_CERT_FILE)
        data = resp.json()
        return jsonify(data)
    except Exception as e:
        return jsonify({"success": False, "message": f"获取Token失败: {str(e)}"})

@app.route('/tokens')
@login_required
@admin_required
def tokens_page():
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "no-store",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Chromium\";v=\"136\", \"Microsoft Edge\";v=\"136\", \"Not.A/Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "veloera-user": str(Config.TOKEN_USER_ID),
        "cookie": Config.TOKEN_COOKIE,
        "Referer": "https://veloera.wei.bi/token",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get("https://veloera.wei.bi/api/token/?p=0&size=100", headers=headers, timeout=10)
        data = resp.json()
        tokens = data.get('data', []) if data.get('success') else []
    except Exception as e:
        tokens = []
    return render_template('tokens.html', tokens=tokens)

@app.route('/api/record/add', methods=['POST'])
@login_required
@admin_required
def add_record():
    """手动录入题目到数据库和缓存"""
    # 验证访问令牌
    if not verify_access_token(request):
        return jsonify({'success': False, 'message': '无效的访问令牌'}), 403
    try:
        data = request.get_json() if request.is_json else request.form
        question = data.get('question', '').strip()
        question_type = data.get('type', '').strip()
        options = data.get('options', '').strip()
        answer = data.get('answer', '').strip()
        # 校验必填
        if not (question and question_type and answer):
            return jsonify({'success': False, 'message': '题目、类型、答案为必填项'}), 400
        # 查重：如已存在则更新，否则插入
        existing = db.query(QARecord).filter(
            QARecord.question == question,
            QARecord.type == question_type,
            QARecord.options == options
        ).first()
        if existing:
            existing.answer = answer
            existing.created_at = datetime.now()
            db.commit()
            msg = '已存在，已覆盖答案'
        else:
            qa_record = QARecord(
                question=question,
                type=question_type,
                options=options,
                answer=answer,
                created_at=datetime.now()
            )
            db.add(qa_record)
            db.commit()
            msg = '已新增'
        # 写入缓存
        if Config.ENABLE_CACHE and cache is not None:
            cache.set(question, answer, question_type, options)
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        logger.error(f"手动录入题目失败: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'录入失败: {str(e)}'}), 500

@app.route('/api/token/<int:token_id>', methods=['GET'])
@login_required
@admin_required
def get_token_detail(token_id):
    """查询单个Token详情，代理远端API"""
    headers = {
        "accept": "application/json, text/plain, */*",
        "veloera-user": str(Config.TOKEN_USER_ID),  # 建议在config.json中配置TOKEN_USER_ID
        "cookie": Config.TOKEN_COOKIE,              # 建议在config.json中配置TOKEN_COOKIE
    }
    try:
        resp = requests.get(f"https://veloera.wei.bi/api/token/{token_id}", headers=headers, timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"success": False, "message": f"获取Token详情失败: {str(e)}"})

@app.route('/api/token/<int:token_id>', methods=['PUT'])
@login_required
@admin_required
def update_token(token_id):
    """修改单个Token，代理远端API"""
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "veloera-user": str(Config.TOKEN_USER_ID),
        "cookie": Config.TOKEN_COOKIE,
    }
    try:
        data = request.get_json()
        data['id'] = token_id  # 确保id正确
        resp = requests.put("https://veloera.wei.bi/api/token/", headers=headers, json=data, timeout=10)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"success": False, "message": f"修改Token失败: {str(e)}"})

if __name__ == '__main__':
    # 开启应用
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)