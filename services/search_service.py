#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级搜索服务
提供智能搜索、关键词高亮、搜索建议等功能
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import or_, and_, func, text
from sqlalchemy.orm import Session
from models.models import QARecord
from services import RedisCache
from config.config import Config

logger = logging.getLogger(__name__)

class SearchService:
    """高级搜索服务"""
    
    def __init__(self, cache: Optional[RedisCache] = None):
        self.cache = cache
        self.search_history_key = "search_history"
        self.hot_searches_key = "hot_searches"
    
    def advanced_search(self, 
                       db_session: Session,
                       query: str = "",
                       question_type: str = "",
                       difficulty: str = "",
                       tags: List[str] = None,
                       date_from: str = "",
                       date_to: str = "",
                       is_favorite: Optional[bool] = None,
                       sort_by: str = "created_at",
                       sort_order: str = "desc",
                       page: int = 1,
                       per_page: int = 10) -> Dict[str, Any]:
        """
        高级搜索功能
        
        Args:
            db_session: 数据库会话
            query: 搜索关键词
            question_type: 题目类型
            difficulty: 难度等级
            tags: 标签列表
            date_from: 开始日期
            date_to: 结束日期
            is_favorite: 是否收藏
            sort_by: 排序字段
            sort_order: 排序方向
            page: 页码
            per_page: 每页数量
            
        Returns:
            搜索结果字典
        """
        try:
            # 构建基础查询
            base_query = db_session.query(QARecord)
            
            # 关键词搜索 - 支持多关键词和模糊匹配
            if query.strip():
                search_terms = self._parse_search_query(query)
                search_conditions = []
                
                for term in search_terms:
                    term_pattern = f"%{term}%"
                    search_conditions.append(
                        or_(
                            QARecord.question.like(term_pattern),
                            QARecord.answer.like(term_pattern),
                            QARecord.options.like(term_pattern)
                        )
                    )
                
                if search_conditions:
                    base_query = base_query.filter(and_(*search_conditions))
            
            # 题目类型筛选
            if question_type:
                base_query = base_query.filter(QARecord.type == question_type)
            
            # 难度筛选
            if difficulty:
                base_query = base_query.filter(QARecord.difficulty == difficulty)
            
            # 标签筛选
            if tags:
                for tag in tags:
                    base_query = base_query.filter(QARecord.tags.like(f"%{tag}%"))
            
            # 日期范围筛选
            if date_from:
                base_query = base_query.filter(QARecord.created_at >= date_from)
            if date_to:
                base_query = base_query.filter(QARecord.created_at <= date_to)
            
            # 收藏状态筛选
            if is_favorite is not None:
                base_query = base_query.filter(QARecord.is_favorite == is_favorite)
            
            # 获取总数
            total_count = base_query.count()
            
            # 排序
            sort_column = getattr(QARecord, sort_by, QARecord.created_at)
            if sort_order.lower() == "desc":
                base_query = base_query.order_by(sort_column.desc())
            else:
                base_query = base_query.order_by(sort_column.asc())
            
            # 分页
            offset = (page - 1) * per_page
            records = base_query.offset(offset).limit(per_page).all()
            
            # 转换为字典并添加高亮
            results = []
            for record in records:
                record_dict = record.to_dict()
                if query.strip():
                    record_dict = self._highlight_keywords(record_dict, query)
                results.append(record_dict)
            
            # 记录搜索历史
            if query.strip():
                self._record_search_history(query)
            
            return {
                'success': True,
                'data': results,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total_count,
                    'pages': (total_count + per_page - 1) // per_page
                },
                'search_info': {
                    'query': query,
                    'filters_applied': {
                        'type': question_type,
                        'difficulty': difficulty,
                        'tags': tags,
                        'date_range': f"{date_from} - {date_to}" if date_from or date_to else None,
                        'is_favorite': is_favorite
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"高级搜索失败: {str(e)}")
            return {
                'success': False,
                'message': f'搜索失败: {str(e)}',
                'data': [],
                'pagination': {'page': page, 'per_page': per_page, 'total': 0, 'pages': 0}
            }
    
    def _parse_search_query(self, query: str) -> List[str]:
        """解析搜索查询，支持引号包围的短语和多关键词"""
        # 处理引号包围的短语
        phrases = re.findall(r'"([^"]*)"', query)
        # 移除引号部分，获取剩余的单词
        remaining = re.sub(r'"[^"]*"', '', query)
        words = remaining.split()
        
        # 合并短语和单词
        terms = phrases + [word for word in words if word.strip()]
        return [term.strip() for term in terms if term.strip()]
    
    def _highlight_keywords(self, record_dict: Dict[str, Any], query: str) -> Dict[str, Any]:
        """为搜索结果添加关键词高亮"""
        search_terms = self._parse_search_query(query)
        
        for field in ['question', 'answer', 'options']:
            if record_dict.get(field):
                content = str(record_dict[field])
                for term in search_terms:
                    # 使用HTML标记高亮关键词
                    pattern = re.compile(re.escape(term), re.IGNORECASE)
                    content = pattern.sub(f'<mark class="search-highlight">{term}</mark>', content)
                record_dict[f'{field}_highlighted'] = content
        
        return record_dict
    
    def get_search_suggestions(self, query: str, limit: int = 5) -> List[str]:
        """获取搜索建议"""
        try:
            if not query.strip() or len(query) < 2:
                return []
            
            # 从缓存获取热门搜索
            hot_searches = self.get_hot_searches(limit * 2)
            
            # 过滤匹配的建议
            suggestions = []
            query_lower = query.lower()
            
            for search_term in hot_searches:
                if query_lower in search_term.lower() and search_term not in suggestions:
                    suggestions.append(search_term)
                    if len(suggestions) >= limit:
                        break
            
            return suggestions
            
        except Exception as e:
            logger.error(f"获取搜索建议失败: {str(e)}")
            return []
    
    def get_search_history(self, limit: int = 10) -> List[str]:
        """获取搜索历史"""
        try:
            if not self.cache:
                return []
            
            history = self.cache.redis.lrange(self.search_history_key, 0, limit - 1)
            return [item.decode('utf-8') if isinstance(item, bytes) else item for item in history]
            
        except Exception as e:
            logger.error(f"获取搜索历史失败: {str(e)}")
            return []
    
    def get_hot_searches(self, limit: int = 10) -> List[str]:
        """获取热门搜索"""
        try:
            if not self.cache:
                return []
            
            # 获取搜索次数排行
            hot_searches = self.cache.redis.zrevrange(self.hot_searches_key, 0, limit - 1)
            return [item.decode('utf-8') if isinstance(item, bytes) else item for item in hot_searches]
            
        except Exception as e:
            logger.error(f"获取热门搜索失败: {str(e)}")
            return []
    
    def _record_search_history(self, query: str):
        """记录搜索历史和热门搜索"""
        try:
            if not self.cache or not query.strip():
                return
            
            # 记录搜索历史（最近搜索）
            self.cache.redis.lpush(self.search_history_key, query)
            self.cache.redis.ltrim(self.search_history_key, 0, 99)  # 保留最近100条
            
            # 记录热门搜索（搜索次数统计）
            self.cache.redis.zincrby(self.hot_searches_key, 1, query)
            
        except Exception as e:
            logger.error(f"记录搜索历史失败: {str(e)}")
    
    def clear_search_history(self):
        """清空搜索历史"""
        try:
            if self.cache:
                self.cache.redis.delete(self.search_history_key)
                return True
        except Exception as e:
            logger.error(f"清空搜索历史失败: {str(e)}")
        return False
    
    def toggle_favorite(self, db_session: Session, question_id: int) -> Dict[str, Any]:
        """切换题目收藏状态"""
        try:
            record = db_session.query(QARecord).filter(QARecord.id == question_id).first()
            if not record:
                return {'success': False, 'message': '题目不存在'}
            
            record.is_favorite = not (record.is_favorite or False)
            db_session.commit()
            
            return {
                'success': True,
                'is_favorite': record.is_favorite,
                'message': '已收藏' if record.is_favorite else '已取消收藏'
            }
            
        except Exception as e:
            logger.error(f"切换收藏状态失败: {str(e)}")
            db_session.rollback()
            return {'success': False, 'message': f'操作失败: {str(e)}'}
    
    def update_view_count(self, db_session: Session, question_id: int):
        """更新题目查看次数"""
        try:
            record = db_session.query(QARecord).filter(QARecord.id == question_id).first()
            if record:
                record.view_count = (record.view_count or 0) + 1
                record.last_viewed = func.now()
                db_session.commit()
                
        except Exception as e:
            logger.error(f"更新查看次数失败: {str(e)}")
            db_session.rollback()
