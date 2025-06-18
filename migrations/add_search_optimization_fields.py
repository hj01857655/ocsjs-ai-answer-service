#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：添加搜索优化相关字段
为QARecord表添加新的字段以支持高级搜索功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from models import get_db_session, close_db_session
import logging

logger = logging.getLogger(__name__)

def add_search_optimization_fields():
    """添加搜索优化相关字段"""

    # 要添加的字段定义
    new_fields = [
        {
            'name': 'question_length',
            'sql': 'ALTER TABLE qa_records ADD COLUMN question_length INTEGER DEFAULT 0',
            'description': '题目长度字段'
        },
        {
            'name': 'is_favorite',
            'sql': 'ALTER TABLE qa_records ADD COLUMN is_favorite BOOLEAN DEFAULT FALSE',
            'description': '收藏状态字段'
        },
        {
            'name': 'view_count',
            'sql': 'ALTER TABLE qa_records ADD COLUMN view_count INTEGER DEFAULT 0',
            'description': '查看次数字段'
        },
        {
            'name': 'last_viewed',
            'sql': 'ALTER TABLE qa_records ADD COLUMN last_viewed DATETIME',
            'description': '最后查看时间字段'
        },
        {
            'name': 'difficulty',
            'sql': 'ALTER TABLE qa_records ADD COLUMN difficulty VARCHAR(10) DEFAULT \'medium\'',
            'description': '难度等级字段'
        },
        {
            'name': 'tags',
            'sql': 'ALTER TABLE qa_records ADD COLUMN tags TEXT',
            'description': '标签字段'
        },
        {
            'name': 'source',
            'sql': 'ALTER TABLE qa_records ADD COLUMN source VARCHAR(100)',
            'description': '题目来源字段'
        },
        {
            'name': 'updated_at',
            'sql': 'ALTER TABLE qa_records ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP',
            'description': '更新时间字段'
        }
    ]

    # 要添加的索引（MySQL语法）
    new_indexes = [
        {
            'name': 'idx_qa_records_type',
            'sql': 'CREATE INDEX idx_qa_records_type ON qa_records(type)',
            'description': '题目类型索引'
        },
        {
            'name': 'idx_qa_records_created_at',
            'sql': 'CREATE INDEX idx_qa_records_created_at ON qa_records(created_at)',
            'description': '创建时间索引'
        },
        {
            'name': 'idx_qa_records_is_favorite',
            'sql': 'CREATE INDEX idx_qa_records_is_favorite ON qa_records(is_favorite)',
            'description': '收藏状态索引'
        },
        {
            'name': 'idx_qa_records_difficulty',
            'sql': 'CREATE INDEX idx_qa_records_difficulty ON qa_records(difficulty)',
            'description': '难度等级索引'
        },
        {
            'name': 'idx_qa_records_view_count',
            'sql': 'CREATE INDEX idx_qa_records_view_count ON qa_records(view_count)',
            'description': '查看次数索引'
        }
    ]

    db_session = None
    try:
        db_session = get_db_session()

        print("🔧 开始数据库迁移：添加搜索优化字段")
        print("=" * 60)

        # 检查表是否存在（兼容MySQL和SQLite）
        try:
            result = db_session.execute(text("SHOW TABLES LIKE 'qa_records'"))
            if not result.fetchone():
                print("❌ qa_records表不存在，请先创建基础表结构")
                return False

            # 获取现有字段（MySQL）
            result = db_session.execute(text("DESCRIBE qa_records"))
            existing_columns = {row[0] for row in result.fetchall()}
        except:
            # 如果是SQLite
            try:
                result = db_session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='qa_records'"))
                if not result.fetchone():
                    print("❌ qa_records表不存在，请先创建基础表结构")
                    return False

                result = db_session.execute(text("PRAGMA table_info(qa_records)"))
                existing_columns = {row[1] for row in result.fetchall()}
            except Exception as e:
                print(f"❌ 无法检查表结构: {str(e)}")
                return False

        print(f"📋 现有字段: {', '.join(sorted(existing_columns))}")

        # 添加新字段
        added_fields = []
        for field in new_fields:
            if field['name'] not in existing_columns:
                try:
                    db_session.execute(text(field['sql']))
                    added_fields.append(field['name'])
                    print(f"✅ 添加字段: {field['name']} - {field['description']}")
                except Exception as e:
                    print(f"⚠️ 添加字段 {field['name']} 失败: {str(e)}")
            else:
                print(f"⏭️ 字段 {field['name']} 已存在，跳过")

        # 提交字段添加
        db_session.commit()

        # 添加索引
        added_indexes = []
        for index in new_indexes:
            try:
                db_session.execute(text(index['sql']))
                added_indexes.append(index['name'])
                print(f"✅ 添加索引: {index['name']} - {index['description']}")
            except Exception as e:
                print(f"⚠️ 添加索引 {index['name']} 失败: {str(e)}")

        # 提交索引添加
        db_session.commit()

        # 更新现有记录的question_length字段
        if 'question_length' in added_fields:
            print("\n🔄 更新现有记录的题目长度...")
            update_sql = """
                UPDATE qa_records
                SET question_length = LENGTH(question)
                WHERE question_length = 0 OR question_length IS NULL
            """
            result = db_session.execute(text(update_sql))
            db_session.commit()
            print(f"✅ 更新了 {result.rowcount} 条记录的题目长度")

        # 验证迁移结果
        print("\n📊 迁移结果验证:")
        try:
            # MySQL语法
            result = db_session.execute(text("DESCRIBE qa_records"))
            final_columns = {row[0] for row in result.fetchall()}
        except:
            # SQLite语法
            try:
                result = db_session.execute(text("PRAGMA table_info(qa_records)"))
                final_columns = {row[1] for row in result.fetchall()}
            except Exception as e:
                print(f"⚠️ 无法验证字段: {str(e)}")
                final_columns = set()

        print(f"📋 最终字段数量: {len(final_columns)}")
        print(f"📋 新增字段: {', '.join(added_fields) if added_fields else '无'}")
        print(f"📋 新增索引: {', '.join(added_indexes) if added_indexes else '无'}")

        # 检查记录数量
        try:
            result = db_session.execute(text("SELECT COUNT(*) FROM qa_records"))
            record_count = result.scalar()
            print(f"📊 总记录数: {record_count}")
        except Exception as e:
            print(f"⚠️ 无法获取记录数量: {str(e)}")

        print("\n🎉 数据库迁移完成！")
        return True

    except Exception as e:
        print(f"\n❌ 迁移失败: {str(e)}")
        if db_session:
            db_session.rollback()
        return False

    finally:
        if db_session:
            close_db_session(db_session)

def rollback_migration():
    """回滚迁移（移除添加的字段）"""

    # SQLite不支持DROP COLUMN，所以需要重建表
    print("⚠️ SQLite不支持直接删除字段，需要手动处理回滚")
    print("如需回滚，请备份数据后重新创建表结构")

    return False

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='搜索优化字段迁移脚本')
    parser.add_argument('--rollback', action='store_true', help='回滚迁移')
    parser.add_argument('--dry-run', action='store_true', help='仅显示将要执行的操作')

    args = parser.parse_args()

    if args.dry_run:
        print("🔍 预览模式：将要执行的操作")
        print("=" * 60)
        print("1. 添加字段: question_length, is_favorite, view_count, last_viewed")
        print("2. 添加字段: difficulty, tags, source, updated_at")
        print("3. 添加索引: type, created_at, is_favorite, difficulty, view_count")
        print("4. 更新现有记录的question_length值")
        print("\n使用 --rollback 参数可以回滚迁移")
        return

    if args.rollback:
        success = rollback_migration()
    else:
        success = add_search_optimization_fields()

    if success:
        print("\n✅ 迁移操作成功完成")
    else:
        print("\n❌ 迁移操作失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
