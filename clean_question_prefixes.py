#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
题目前缀清理脚本
用于清理数据库中已有题目的前缀，如"20. (单选题，1分)"和"55. (判断题，1分)"
"""

import re
import logging
import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入项目模块
from models.models import QARecord, get_db_session, close_db_session
from config.config import Config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/clean_prefixes.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('clean_prefixes')

def clean_question_prefix(question_text):
    """
    清理题目前缀
    :param question_text: 原始题目文本
    :return: 清理后的题目文本
    """
    if not question_text:
        return question_text
    
    # 保存原始内容用于日志记录
    original_content = question_text
    
    # 先尝试去除常见的序号+题型前缀格式
    question_text = re.sub(r'^\s*\d+\.?\s*[\(\uff08][^\)\uff09]+[\)\uff09]\s*', '', question_text, flags=re.I)
    
    # 再尝试去除可能的其他格式前缀
    question_text = re.sub(r'^\s*\d+\.?\s*', '', question_text, flags=re.I)  # 去除只有序号的前缀
    question_text = re.sub(r'^\s*[\(\uff08][^\)\uff09]+[\)\uff09]\s*', '', question_text, flags=re.I)  # 去除只有括号的前缀
    
    # 去除可能的空格
    question_text = question_text.strip()
    
    # 如果内容发生了变化，记录日志
    if original_content != question_text:
        logger.info(f'题目前缀去除: 原始="{original_content[:50]}..." → 处理后="{question_text[:50]}..."')
    
    return question_text

def clean_all_questions():
    """
    清理数据库中所有题目的前缀
    """
    session = get_db_session()
    try:
        # 获取所有题目记录
        records = session.query(QARecord).all()
        logger.info(f"开始清理题目前缀，共找到 {len(records)} 条记录")
        
        # 统计信息
        total = len(records)
        cleaned = 0
        unchanged = 0
        
        # 处理每条记录
        for record in records:
            original_question = record.question
            cleaned_question = clean_question_prefix(original_question)
            
            if original_question != cleaned_question:
                record.question = cleaned_question
                cleaned += 1
            else:
                unchanged += 1
                
            # 每处理100条记录提交一次，避免事务过大
            if (cleaned + unchanged) % 100 == 0:
                session.commit()
                logger.info(f"已处理 {cleaned + unchanged}/{total} 条记录")
        
        # 提交剩余的更改
        session.commit()
        logger.info(f"题目前缀清理完成！总记录数: {total}, 已清理: {cleaned}, 无需清理: {unchanged}")
        
        return {
            'total': total,
            'cleaned': cleaned,
            'unchanged': unchanged
        }
    except Exception as e:
        session.rollback()
        logger.error(f"清理题目前缀时出错: {str(e)}")
        raise
    finally:
        close_db_session(session)

def create_backup():
    """
    在清理前创建数据库备份 - MySQL版本
    使用mysqldump工具备份qa_records表
    """
    import os
    import subprocess
    from datetime import datetime
    from config.config import Config
    
    # 确保备份目录存在
    backup_dir = 'backups'
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    # 创建带时间戳的备份文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'qa_records_backup_{timestamp}.sql')
    
    try:
        # 构建mysqldump命令 - 只备份qa_records表
        cmd = [
            'mysqldump',
            f'--host={Config.DB_HOST}',
            f'--port={Config.DB_PORT}',
            f'--user={Config.DB_USER}',
            f'--password={Config.DB_PASSWORD}',
            f'{Config.DB_NAME}',
            'qa_records',
            f'--result-file={backup_path}'
        ]
        
        # 执行备份命令
        logger.info(f"开始备份数据库表 qa_records...")
        subprocess.run(cmd, check=True)
        logger.info(f"数据库表备份已创建: {backup_path}")
        
        return backup_path
    except Exception as e:
        logger.error(f"创建数据库备份失败: {str(e)}")
        print(f"警告: 无法创建数据库备份: {str(e)}")
        print("将继续执行清理操作，但没有备份可恢复。")
        
        # 询问是否继续
        confirm = input("没有备份的情况下是否继续? (y/n): ")
        if confirm.lower() != 'y':
            logger.info("操作已取消")
            exit(0)
            
        return None

if __name__ == "__main__":
    try:
        # 创建日志目录
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        # 尝试创建备份
        try:
            backup_path = create_backup()
            if backup_path:
                logger.info(f"数据库已备份到: {backup_path}")
                print(f"数据库已备份到: {backup_path}")
                
                # 备份成功后确认继续
                confirm = input("数据库已备份。是否继续清理题目前缀？(y/n): ")
                if confirm.lower() != 'y':
                    logger.info("操作已取消")
                    exit(0)
        except Exception as e:
            logger.error(f"备份失败: {str(e)}")
            print(f"警告: 无法创建备份: {str(e)}")
            confirm = input("没有备份的情况下是否继续? (请谨慎考虑) (y/n): ")
            if confirm.lower() != 'y':
                logger.info("操作已取消")
                exit(0)
        
        # 执行清理
        print("开始清理题目前缀...")
        start_time = datetime.now()
        result = clean_all_questions()
        end_time = datetime.now()
        
        # 输出结果
        duration = (end_time - start_time).total_seconds()
        logger.info(f"清理完成！耗时: {duration:.2f}秒")
        logger.info(f"总记录数: {result['total']}")
        logger.info(f"已清理记录: {result['cleaned']}")
        logger.info(f"无需清理记录: {result['unchanged']}")
        
        print("\
清理结果摘要:")
        print(f"总记录数: {result['total']}")
        print(f"已清理记录: {result['cleaned']}")
        print(f"无需清理记录: {result['unchanged']}")
        print(f"耗时: {duration:.2f}秒")
        print(f"详细日志请查看: logs/clean_prefixes.log")
        
    except Exception as e:
        logger.error(f"执行过程中出错: {str(e)}")
        print(f"错误: {str(e)}")
        print("操作已中止。详细信息请查看日志文件。")
