from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, send_file, current_app, g
from models import QARecord, get_db_session, close_db_session
from utils import login_required, admin_required
from utils.logger import app_logger as logger
from utils.question_cleaner import clean_question_prefix
from services.search_service import SearchService
from services import RedisCache
from config.config import Config
from datetime import datetime
import time
# 使用系统日志记录器，确保题目录入日志显示在日志页面上

# 简单的内存缓存
class SimpleCache:
    def __init__(self):
        self.cache = {}

    def clear(self):
        """清除所有缓存"""
        cleared_count = len(self.cache)
        self.cache.clear()
        return cleared_count

# 创建全局缓存实例
question_cache = SimpleCache()

# 创建蓝图
questions_bp = Blueprint('questions', __name__)

# 初始化搜索服务
def get_search_service():
    """获取搜索服务实例"""
    try:
        # 尝试获取Redis缓存
        cache = None
        if hasattr(Config, 'REDIS_ENABLED') and Config.REDIS_ENABLED:
            from services import RedisCache
            cache = RedisCache(Config.CACHE_EXPIRATION)
        return SearchService(cache)
    except Exception as e:
        logger.warning(f"初始化搜索服务失败，使用基础功能: {str(e)}")
        return SearchService(None)

def get_cached_type_counts():
    """获取缓存的题型统计数据"""
    cache_key = 'question_type_counts'

    # 尝试从缓存获取
    if hasattr(question_cache, 'cache') and cache_key in question_cache.cache:
        cached_data = question_cache.cache[cache_key]
        # 检查缓存是否过期（5分钟）
        if time.time() - cached_data['timestamp'] < 300:
            return cached_data['data']

    # 缓存过期或不存在，重新查询
    from sqlalchemy import func
    type_stats = g.db.query(
        QARecord.type,
        func.count(QARecord.id).label('count')
    ).group_by(QARecord.type).all()

    # 构建统计字典
    type_counts = {
        'all': sum(stat.count for stat in type_stats),
        'single': 0,
        'multiple': 0,
        'judgement': 0,
        'completion': 0,
        'short': 0,
        'essay': 0,
        'calculation': 0,
        'analysis': 0,
        'case': 0,
        'matching': 0,
    }

    # 填充实际统计数据
    for stat in type_stats:
        if stat.type in type_counts:
            type_counts[stat.type] = stat.count

    # 缓存数据
    question_cache.cache[cache_key] = {
        'data': type_counts,
        'timestamp': time.time()
    }

    return type_counts

@questions_bp.route('/questions', methods=['GET'])
@login_required
def questions():
    """题目列表页面，支持高级搜索、分页、类型筛选"""
    start_time = time.time()
    current_year = datetime.now().year

    # 获取搜索参数
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 50)  # 限制每页最大数量
    search_query = request.args.get('q', '')
    current_type = request.args.get('type', '')
    difficulty = request.args.get('difficulty', '')
    is_favorite = request.args.get('favorite')
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')

    # 转换收藏状态参数
    favorite_filter = None
    if is_favorite == 'true':
        favorite_filter = True
    elif is_favorite == 'false':
        favorite_filter = False

    # 使用高级搜索服务
    search_service = get_search_service()
    search_result = search_service.advanced_search(
        db_session=g.db,
        query=search_query,
        question_type=current_type,
        difficulty=difficulty,
        is_favorite=favorite_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page
    )

    # 使用缓存的题型统计
    type_counts = get_cached_type_counts()

    # 异步获取搜索历史和热门搜索（简化版本）
    search_history = []
    hot_searches = []
    try:
        search_history = search_service.get_search_history(5)  # 减少数量
        hot_searches = search_service.get_hot_searches(5)     # 减少数量
    except Exception as e:
        logger.warning(f"获取搜索历史失败: {str(e)}")

    end_time = time.time()
    duration = round(end_time - start_time, 3)
    logger.info(f"题库页面加载完成，耗时: {duration}秒")

    return render_template(
        'questions.html',
        records=search_result.get('data', []),
        total_pages=search_result.get('pagination', {}).get('pages', 0),
        page=page,
        per_page=per_page,
        search_query=search_query,
        current_type=current_type,
        difficulty=difficulty,
        is_favorite=is_favorite,
        sort_by=sort_by,
        sort_order=sort_order,
        type_counts=type_counts,
        search_history=search_history,
        hot_searches=hot_searches,
        current_year=current_year,
        search_success=search_result.get('success', True)
    )

@questions_bp.route('/api/questions/export', methods=['GET'])
@login_required
def export_questions():
    """导出题库为CSV文件，支持类型和关键词筛选"""
    start_time = time.time()
    client_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '未知')
    logger.info(f"开始导出题库数据 | IP={client_ip} | User-Agent={user_agent}")

    try:
        question_type = request.args.get('type', '')
        search_query = request.args.get('q', '')
        logger.info(f"导出条件: 类型={question_type or '全部'}, 关键词='{search_query}'")

        query = g.db.query(QARecord)
        if search_query:
            query = query.filter(QARecord.question.like(f'%{search_query}%') | QARecord.answer.like(f'%{search_query}%'))
        if question_type:
            query = query.filter(QARecord.type == question_type)
        records = query.all()
        logger.info(f"查询到 {len(records)} 条题目记录")
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', '问题', '类型', '选项', '答案', '创建时间'])
        for record in records:
            writer.writerow([
                record.id,
                record.question,
                record.type or '未知',
                record.options or '',
                record.answer,
                record.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        from flask import Response
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment;filename=questions.csv'}
        )

        end_time = time.time()
        duration = round(end_time - start_time, 2)
        logger.info(f"导出题库数据成功 | 总计 {len(records)} 条记录 | 耗时 {duration} 秒")
        return response
    except Exception as e:
        end_time = time.time()
        duration = round(end_time - start_time, 2)
        logger.error(f"导出题库数据失败: {str(e)} | 耗时 {duration} 秒")
        return jsonify({'success': False, 'message': f'导出题库数据失败: {str(e)}'}), 500

@questions_bp.route('/api/questions/import', methods=['POST'])
@login_required
def import_questions():
    """批量导入题目，上传CSV文件"""
    start_time = time.time()
    client_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '未知')
    logger.info(f"开始从 CSV 文件导入题目 | IP={client_ip} | User-Agent={user_agent}")

    try:
        if 'file' not in request.files:
            logger.warning("没有上传文件")
            return jsonify({'success': False, 'message': '没有上传文件'}), 400

        file = request.files['file']
        if file.filename == '':
            logger.warning("没有选择文件")
            return jsonify({'success': False, 'message': '没有选择文件'}), 400

        if not file.filename.endswith('.csv'):
            logger.warning(f"不支持的文件类型: {file.filename}")
            return jsonify({'success': False, 'message': '只支持导入CSV文件'}), 400

        logger.info(f"开始处理CSV文件: {file.filename}")
        import csv
        import io
        stream = io.StringIO(file.stream.read().decode('utf-8'))
        reader = csv.reader(stream)
        next(reader)
        imported_count = 0
        error_count = 0
        for row in reader:
            try:
                if len(row) < 5:
                    error_count += 1
                    continue
                question = row[1].strip()
                question_type = row[2].strip() if row[2].strip() != '未知' else None
                options = row[3].strip()
                answer = row[4].strip()
                existing = g.db.query(QARecord).filter(
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
                    g.db.add(qa_record)
                imported_count += 1
            except Exception as e:
                error_count += 1
        g.db.commit()
        end_time = time.time()
        duration = round(end_time - start_time, 2)
        logger.info(f"CSV导入完成: 成功 {imported_count} 条, 失败 {error_count} 条 | 耗时 {duration} 秒")
        return jsonify({'success': True, 'message': f'成功导入{imported_count}条记录，失败{error_count}条'})
    except Exception as e:
        end_time = time.time()
        duration = round(end_time - start_time, 2)
        logger.error(f"CSV导入失败: {str(e)} | 耗时 {duration} 秒")
        return jsonify({'success': False, 'message': f'导入题库数据失败: {str(e)}'}), 500

@questions_bp.route('/api/questions/batch-delete', methods=['POST'])
@login_required
def batch_delete_questions():
    """批量删除题目，参数为record_ids列表"""
    start_time = time.time()
    client_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '未知')
    logger.info(f"开始批量删除题目 | IP={client_ip} | User-Agent={user_agent}")

    try:
        data = request.get_json()
        record_ids = data.get('record_ids', [])

        if not record_ids:
            logger.warning("未提供要删除的记录ID")
            return jsonify({'success': False, 'message': '未提供要删除的记录ID'}), 400

        logger.info(f"尝试删除 {len(record_ids)} 条记录, IDs: {record_ids[:5]}...")
        records = g.db.query(QARecord).filter(QARecord.id.in_(record_ids)).all()

        if not records:
            logger.warning(f"未找到要删除的记录, IDs: {record_ids}")
            return jsonify({'success': False, 'message': '未找到要删除的记录'}), 404

        # 记录删除的题目类型分布
        type_counts = {}
        for record in records:
            record_type = record.type or '未知'
            type_counts[record_type] = type_counts.get(record_type, 0) + 1
            g.db.delete(record)

        g.db.commit()
        end_time = time.time()
        duration = round(end_time - start_time, 2)
        logger.info(f"批量删除成功: 共 {len(records)} 条记录 | 类型分布: {type_counts} | 耗时 {duration} 秒")
        return jsonify({'success': True, 'message': f'成功删除{len(records)}条记录'})
    except Exception as e:
        end_time = time.time()
        duration = round(end_time - start_time, 2)
        logger.error(f"批量删除失败: {str(e)} | 耗时 {duration} 秒")
        return jsonify({'success': False, 'message': f'发生错误: {str(e)}'}), 500

# 新增高级搜索API端点
@questions_bp.route('/api/questions/search', methods=['GET', 'POST'])
@login_required
def api_advanced_search():
    """高级搜索API"""
    try:
        if request.method == 'GET':
            # GET请求从URL参数获取
            search_params = {
                'query': request.args.get('q', ''),
                'question_type': request.args.get('type', ''),
                'difficulty': request.args.get('difficulty', ''),
                'is_favorite': request.args.get('favorite'),
                'sort_by': request.args.get('sort', 'created_at'),
                'sort_order': request.args.get('order', 'desc'),
                'page': request.args.get('page', 1, type=int),
                'per_page': request.args.get('per_page', 10, type=int)
            }
        else:
            # POST请求从JSON获取
            data = request.get_json() or {}
            search_params = {
                'query': data.get('query', ''),
                'question_type': data.get('type', ''),
                'difficulty': data.get('difficulty', ''),
                'tags': data.get('tags', []),
                'date_from': data.get('date_from', ''),
                'date_to': data.get('date_to', ''),
                'is_favorite': data.get('is_favorite'),
                'sort_by': data.get('sort_by', 'created_at'),
                'sort_order': data.get('sort_order', 'desc'),
                'page': data.get('page', 1),
                'per_page': data.get('per_page', 10)
            }

        # 转换收藏状态参数
        if search_params['is_favorite'] == 'true':
            search_params['is_favorite'] = True
        elif search_params['is_favorite'] == 'false':
            search_params['is_favorite'] = False
        else:
            search_params['is_favorite'] = None

        # 执行搜索
        search_service = get_search_service()
        result = search_service.advanced_search(g.db, **search_params)

        return jsonify(result)

    except Exception as e:
        logger.error(f"高级搜索API失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'搜索失败: {str(e)}',
            'data': [],
            'pagination': {'page': 1, 'per_page': 10, 'total': 0, 'pages': 0}
        }), 500

@questions_bp.route('/api/questions/suggestions', methods=['GET'])
@login_required
def api_search_suggestions():
    """搜索建议API"""
    try:
        query = request.args.get('q', '')
        limit = request.args.get('limit', 5, type=int)

        search_service = get_search_service()
        suggestions = search_service.get_search_suggestions(query, limit)

        return jsonify({
            'success': True,
            'suggestions': suggestions
        })

    except Exception as e:
        logger.error(f"获取搜索建议失败: {str(e)}")
        return jsonify({
            'success': False,
            'suggestions': []
        }), 500

@questions_bp.route('/api/questions/history', methods=['GET', 'DELETE'])
@login_required
def api_search_history():
    """搜索历史API"""
    try:
        search_service = get_search_service()

        if request.method == 'GET':
            limit = request.args.get('limit', 10, type=int)
            history = search_service.get_search_history(limit)
            hot_searches = search_service.get_hot_searches(limit)

            return jsonify({
                'success': True,
                'history': history,
                'hot_searches': hot_searches
            })

        elif request.method == 'DELETE':
            success = search_service.clear_search_history()
            return jsonify({
                'success': success,
                'message': '搜索历史已清空' if success else '清空失败'
            })

    except Exception as e:
        logger.error(f"搜索历史API失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'操作失败: {str(e)}'
        }), 500

@questions_bp.route('/api/questions/<int:question_id>/favorite', methods=['POST'])
@login_required
def api_toggle_favorite(question_id):
    """切换题目收藏状态API"""
    try:
        search_service = get_search_service()
        result = search_service.toggle_favorite(g.db, question_id)

        return jsonify(result)

    except Exception as e:
        logger.error(f"切换收藏状态失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'操作失败: {str(e)}'
        }), 500

@questions_bp.route('/api/questions/<int:question_id>/view', methods=['POST'])
@login_required
def api_update_view_count(question_id):
    """更新题目查看次数API"""
    try:
        search_service = get_search_service()
        search_service.update_view_count(g.db, question_id)

        return jsonify({
            'success': True,
            'message': '查看次数已更新'
        })

    except Exception as e:
        logger.error(f"更新查看次数失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'操作失败: {str(e)}'
        }), 500

@questions_bp.route('/api/questions/add', methods=['POST', 'OPTIONS'])
def add_single_record():
    """单个题目录入接口"""
    # 如果是OPTIONS请求，直接返回空响应与必要的CORS头
    if request.method == 'OPTIONS':
        response = jsonify({})
        # 获取请求的Origin头
        origin = request.headers.get('Origin', '')
        # 允许的来源列表
        allowed_origins = ["https://mooc2-ans.chaoxing.com", "http://localhost:8080", "http://127.0.0.1:8080"]

        # 如果请求的Origin在允许列表中，则设置对应的头
        if origin in allowed_origins:
            response.headers.add('Access-Control-Allow-Origin', origin)
            response.headers.add('Access-Control-Allow-Credentials', 'true')
        else:
            # 如果不在允许列表中，使用默认的第一个来源
            response.headers.add('Access-Control-Allow-Origin', allowed_origins[0])

        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        response.headers.add('Access-Control-Max-Age', '600')
        return response

    start_time = time.time()
    client_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '未知')
    logger.info(f"开始录入单个题目到数据库")
    logger.info(f"请求来源: IP={client_ip}, User-Agent={user_agent}")

    # 获取当前请求的数据库会话
    db_session = getattr(g, 'db', None)
    if not db_session:
        return jsonify({'success': False, 'message': '数据库会话初始化失败'}), 500

    try:
        # 获取请求数据
        data = request.get_json()

        # 检查是否是批量导入格式（包含questions数组）
        if 'questions' in data and isinstance(data['questions'], list):
            # 批量导入模式
            questions_data = data['questions']
            success_count = 0
            error_count = 0
            skip_count = 0  # 跳过的重复题目计数

            # 使用集合记录已处理的题目特征，避免重复处理
            processed_questions = set()

            for item in questions_data:
                question = item.get('question', '')
                # 清理题目前缀
                question = clean_question_prefix(question)
                question_type = item.get('type', '')
                options = item.get('options', '')
                answer = item.get('answer', '')

                if not question or not question_type or not answer:
                    error_count += 1
                    continue

                # 创建题目特征码，用于检测当前批次中的重复题目
                question_signature = f"{question}|{question_type}|{options}"

                # 检查是否在当前批次中已处理过相同的题目
                if question_signature in processed_questions:
                    skip_count += 1
                    logger.info(f"跳过重复题目: {question[:30]}...")
                    continue

                # 添加到已处理集合
                processed_questions.add(question_signature)

                # 查重：如已存在则更新，否则插入
                existing = db_session.query(QARecord).filter(
                    QARecord.question == question,
                    QARecord.type == question_type,
                    QARecord.options == options
                ).first()

                if existing:
                    # 检查答案是否相同，如果相同则不需要更新
                    if existing.answer == answer:
                        skip_count += 1
                        logger.info(f"跳过数据库中已存在的相同题目: {question[:30]}...")
                        continue

                    # 答案不同，更新答案
                    existing.answer = answer
                    existing.created_at = datetime.now()
                    logger.info(f"更新已存在题目的答案: {question[:30]}...")
                else:
                    # 新题目，添加到数据库
                    qa_record = QARecord(
                        question=question,
                        type=question_type,
                        options=options,
                        answer=answer,
                        created_at=datetime.now()
                    )
                    db_session.add(qa_record)
                    logger.info(f"添加新题目: {question[:30]}...")

                success_count += 1

            db_session.commit()
            message = f'成功导入 {success_count} 道题目'
            if skip_count > 0:
                message += f', 跳过 {skip_count} 道重复题目'
            if error_count > 0:
                message += f', {error_count} 道题目格式错误'
        else:
            # 单题导入模式
            question = data.get('question', '')
            # 清理题目前缀
            question = clean_question_prefix(question)
            question_type = data.get('type', '')
            options = data.get('options', '')
            answer = data.get('answer', '')

            if not question or not question_type or not answer:
                return jsonify({'success': False, 'message': '缺少必要字段（题目、类型、答案）'}), 400

            # 查重：如已存在则更新，否则插入
            existing = db_session.query(QARecord).filter(
                QARecord.question == question,
                QARecord.type == question_type,
                QARecord.options == options
            ).first()

            if existing:
                existing.answer = answer
                existing.created_at = datetime.now()
                message = '题目已存在，已更新答案'
            else:
                qa_record = QARecord(
                    question=question,
                    type=question_type,
                    options=options,
                    answer=answer,
                    created_at=datetime.now()
                )
                db_session.add(qa_record)
                message = '题目已成功录入'

            # 事务已在各自的分支中提交

        # 记录处理时间
        process_time = time.time() - start_time
        logger.info(f"单个题目录入完成 (耗时: {process_time:.2f}秒)")

        # 创建响应并添加CORS头
        response = jsonify({
            'success': True,
            'message': message
        })

        # 获取请求的Origin头
        origin = request.headers.get('Origin', '')
        # 允许的来源列表
        allowed_origins = ["https://mooc2-ans.chaoxing.com", "http://localhost:8080", "http://127.0.0.1:8080"]

        # 如果请求的Origin在允许列表中，则设置对应的头
        if origin in allowed_origins:
            response.headers.add('Access-Control-Allow-Origin', origin)
            response.headers.add('Access-Control-Allow-Credentials', 'true')
        else:
            # 如果不在允许列表中，使用默认的第一个来源
            response.headers.add('Access-Control-Allow-Origin', allowed_origins[0])

        return response

    except Exception as e:
        logger.error(f"录入单个题目时发生错误: {str(e)}", exc_info=True)
        # 创建错误响应并添加CORS头
        response = jsonify({
            'success': False,
            'message': f'发生错误: {str(e)}'
        })

        # 获取请求的Origin头
        origin = request.headers.get('Origin', '')
        # 允许的来源列表
        allowed_origins = ["https://mooc2-ans.chaoxing.com", "http://localhost:8080", "http://127.0.0.1:8080"]

        # 如果请求的Origin在允许列表中，则设置对应的头
        if origin in allowed_origins:
            response.headers.add('Access-Control-Allow-Origin', origin)
            response.headers.add('Access-Control-Allow-Credentials', 'true')
        else:
            # 如果不在允许列表中，使用默认的第一个来源
            response.headers.add('Access-Control-Allow-Origin', allowed_origins[0])

        response.status_code = 500
        return response

@questions_bp.route('/api/import_questions', methods=['POST'])
# 移除登录限制，允许外部系统和脚本直接调用
def import_questions_json():
    """批量导入题目"""
    start_time = time.time()
    client_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '未知')
    logger.info(f"开始录入题目到数据库")
    logger.info(f"请求来源: IP={client_ip}, User-Agent={user_agent}")

    # 获取当前请求的数据库会话
    db_session = getattr(g, 'db', None)
    if not db_session:
        return jsonify({'success': False, 'message': '数据库会话初始化失败'}), 500

    try:
        # 获取请求数据
        data = request.get_json()

        # 兼容两种格式：直接的数组和 { questions: [...] } 格式
        if isinstance(data, dict) and 'questions' in data:
            questions = data['questions']
            logger.info("检测到 { questions: [...] } 格式的请求数据")
        elif isinstance(data, list):
            questions = data
            logger.info("检测到直接的数组格式请求数据")
        else:
            return jsonify({'success': False, 'message': '无效的数据格式，请提供JSON数组或 { questions: [...] } 格式'}), 400

        # 检查数组是否为空
        if not questions or not isinstance(questions, list):
            return jsonify({'success': False, 'message': '题目数组为空或格式不正确'}), 400
        logger.info(f"收到题目数量: {len(questions)}")

        # 验证题型
        valid_types = ['single', 'multiple', 'judgement', 'completion', 'short', 'essay', 'calculation', 'analysis', 'case', 'matching']

        # 统计题型数量
        type_counts = {}
        for item in questions:
            q_type = item.get('type', '未知')
            # 确保题型有效
            if q_type not in valid_types and q_type != '未知':
                logger.warning(f"发现未知题型: {q_type}，将使用原始值")
            type_counts[q_type] = type_counts.get(q_type, 0) + 1
        logger.info(f"题型分布: {type_counts}")

        imported_count = 0
        error_count = 0
        updated_count = 0

        # 处理题目导入
        try:
            for idx, item in enumerate(questions):
                try:
                    question = item.get('question', '').strip()
                    question_type = item.get('type', '').strip() or None
                    options = item.get('options', '').strip()
                    answer = item.get('answer', '').strip()

                    # 记录题目信息摘要
                    question_summary = question[:30] + '...' if len(question) > 30 else question
                    logger.debug(f"处理第{idx+1}题: 类型={question_type}, 题干={question_summary}")

                    if not question or not answer:
                        logger.warning(f"第{idx+1}题缺少题干或答案，已跳过")
                        error_count += 1
                        continue

                    # 使用try-except包裹查询操作，防止查询异常
                    try:
                        existing = db_session.query(QARecord).filter(
                            QARecord.question == question,
                            QARecord.type == question_type,
                            QARecord.options == options
                        ).first()
                    except Exception as query_error:
                        logger.error(f"查询第{idx+1}题时出错: {str(query_error)}")
                        db_session.rollback()
                        error_count += 1
                        continue

                    if existing:
                        # 检查所有属性是否完全一致
                        if (existing.question == question and
                            existing.type == question_type and
                            existing.options == options and
                            existing.answer == answer):
                            # 完全相同的题目，直接跳过
                            logger.debug(f"第{idx+1}题已存在，ID={existing.id}，完全一致，跳过处理")
                            continue

                        # 检查答案是否一致，如果只有答案不同，才更新答案
                        if existing.answer != answer:
                            logger.info(f"第{idx+1}题已存在，ID={existing.id}，答案不同，更新答案")
                            existing.answer = answer
                            existing.created_at = datetime.now()
                            updated_count += 1
                        else:
                            # 答案一致但其他属性有变化，更新其他属性
                            changes = []
                            if existing.question != question:
                                existing.question = question
                                changes.append('题干')
                            if existing.type != question_type:
                                existing.type = question_type
                                changes.append('类型')
                            if existing.options != options:
                                existing.options = options
                                changes.append('选项')

                            if changes:
                                logger.info(f"第{idx+1}题已存在，ID={existing.id}，更新了{', '.join(changes)}")
                                existing.created_at = datetime.now()
                                updated_count += 1
                            else:
                                # 这种情况不应该发生，因为前面的完全一致检查应该已经跳过了
                                logger.warning(f"第{idx+1}题已存在，ID={existing.id}，逻辑错误，没有变化但未被跳过")
                                continue
                    else:
                        logger.info(f"第{idx+1}题为新题目，添加到数据库")
                        qa_record = QARecord(
                            question=question,
                            type=question_type,
                            options=options,
                            answer=answer,
                            created_at=datetime.now()
                        )
                        db_session.add(qa_record)

                    imported_count += 1

                    # 每处理一定数量的题目后进行一次提交，减少单次事务的大小
                    if (idx + 1) % 10 == 0:
                        try:
                            db_session.commit()
                            logger.debug(f"已提交前 {idx+1} 题的修改")
                        except Exception as commit_error:
                            logger.error(f"提交事务时出错: {str(commit_error)}")
                            db_session.rollback()
                            error_count += 1

                except Exception as e:
                    logger.error(f"处理第{idx+1}题时出错: {str(e)}")
                    error_count += 1
                    # 确保当前事务状态正常
                    try:
                        db_session.rollback()
                    except:
                        pass

            # 最终提交所有修改
            try:
                db_session.commit()
                logger.info(f"所有修改已提交到数据库")
            except Exception as final_commit_error:
                logger.error(f"最终提交时出错: {str(final_commit_error)}")
                db_session.rollback()
                error_count += len(questions) - imported_count  # 将所有未成功导入的题目计入错误数
                imported_count = 0  # 重置导入数，因为所有修改都被回滚了
        except Exception as outer_error:
            logger.error(f"批量导入过程中发生严重错误: {str(outer_error)}")
            db_session.rollback()
            error_count = len(questions)
            imported_count = 0

        end_time = time.time()
        duration = round(end_time - start_time, 2)

        result_msg = f'成功导入{imported_count}条记录(其中更新{updated_count}条)，失败{error_count}条，耗时{duration}秒'
        logger.info(f"录入完成: {result_msg}")

        return jsonify({
            'success': True,
            'message': result_msg,
            'stats': {
                'total': len(questions),
                'imported': imported_count,
                'updated': updated_count,
                'failed': error_count,
                'duration': duration,
                'type_counts': type_counts
            }
        })
    except Exception as e:
        end_time = time.time()
        duration = round(end_time - start_time, 2)
        error_msg = f'导入题库数据失败: {str(e)}，耗时{duration}秒'
        logger.error(error_msg)
        return jsonify({'success': False, 'message': error_msg}), 500

# 6. 题目详情接口
@questions_bp.route('/api/questions/<int:question_id>', methods=['GET'])
@login_required
def get_question_detail(question_id):
    """获取单个题目的详细信息"""
    client_ip = request.remote_addr
    logger.info(f"查询题目详情 ID={question_id} | IP={client_ip}")

    record = g.db.query(QARecord).filter(QARecord.id == question_id).first()
    if not record:
        logger.warning(f"未找到题目 ID={question_id}")
        return jsonify({'success': False, 'message': '未找到该题目'}), 404

    logger.info(f"成功获取题目详情 ID={question_id}, 类型={record.type or '未知'}")
    return jsonify({
        'success': True,
        'data': {
            'id': record.id,
            'question': record.question,
            'type': record.type,
            'options': record.options,
            'answer': record.answer,
            'created_at': record.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
    })

# 7. 题目编辑/更新接口
@questions_bp.route('/api/questions/<int:question_id>', methods=['PUT'])
@login_required
def update_question(question_id):
    """修改已存在的题目"""
    start_time = time.time()
    client_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '未知')
    logger.info(f"开始更新题目 ID={question_id} | IP={client_ip} | User-Agent={user_agent}")

    record = g.db.query(QARecord).filter(QARecord.id == question_id).first()
    if not record:
        logger.warning(f"更新失败: 未找到题目 ID={question_id}")
        return jsonify({'success': False, 'message': '未找到该题目'}), 404

    data = request.get_json()
    old_type = record.type

    # 记录更新前的值
    logger.info(f"更新前: 类型={old_type or '未知'}, 题干={record.question[:30]}...")

    record.question = data.get('question', record.question)
    record.type = data.get('type', record.type)
    record.options = data.get('options', record.options)
    record.answer = data.get('answer', record.answer)
    record.created_at = datetime.now()

    g.db.commit()
    end_time = time.time()
    duration = round(end_time - start_time, 2)

    # 记录更新后的值
    logger.info(f"题目更新成功: ID={question_id}, 类型变化: {old_type or '未知'} -> {record.type or '未知'} | 耗时 {duration} 秒")
    return jsonify({'success': True, 'message': '题目更新成功'})

# 8. 单题删除接口
@questions_bp.route('/api/questions/<int:question_id>', methods=['DELETE'])
@login_required
def delete_question(question_id):
    """删除单个题目"""
    client_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '未知')
    logger.info(f"开始删除题目 ID={question_id} | IP={client_ip} | User-Agent={user_agent}")

    record = g.db.query(QARecord).filter(QARecord.id == question_id).first()
    if not record:
        logger.warning(f"删除失败: 未找到题目 ID={question_id}")
        return jsonify({'success': False, 'message': '未找到该题目'}), 404

    # 记录被删除题目的信息
    question_summary = record.question[:30] + '...' if len(record.question) > 30 else record.question
    logger.info(f"删除题目: ID={question_id}, 类型={record.type or '未知'}, 题干={question_summary}")

    g.db.delete(record)
    g.db.commit()
    logger.info(f"题目删除成功: ID={question_id}")
    return jsonify({'success': True, 'message': '题目删除成功'})