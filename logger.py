# -*- coding: utf-8 -*-
"""
日志工具模块
提供统一的日志记录机制
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

from config import Config

class Logger:
    """日志管理类"""
    
    def __init__(self, name, log_dir="logs"):
        """
        初始化日志记录器
        
        Args:
            name: 日志记录器名称
            log_dir: 日志文件保存目录
        """
        self.name = name
        self.log_dir = log_dir
        
        # 创建日志目录
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 设置日志文件名，包含日期
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"{name}_{today}.log")
        
        # 创建日志记录器
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        # 如果已经添加了处理器，则不再添加
        if self.logger.handlers:
            return
        
        # 创建文件处理器，设置轮转，最大10MB，保留5个备份
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        # 注释掉控制台处理器
        # console_handler = logging.StreamHandler(sys.stdout)
        # console_handler.setLevel(logging.ERROR)  # 只显示ERROR级别以上
        
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        # console_handler.setFormatter(formatter)
        
        # 将处理器添加到记录器
        self.logger.addHandler(file_handler)
        # self.logger.addHandler(console_handler)
    
    def get_logger(self):
        """获取日志记录器"""
        return self.logger
    
    @staticmethod
    def get_latest_logs(max_lines=1000):
        """
        获取最新的日志内容
        
        Args:
            max_lines: 最大返回行数
            
        Returns:
            str: 日志内容
        """
        try:
            # 获取当前日期
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = os.path.join("logs", f"app.log")  # 使用固定的app.log文件
            
            # 如果app.log不存在，尝试获取最近的日志文件
            if not os.path.exists(log_file):
                log_file = os.path.join("logs", f"ai_answer_service_{today}.log")
                
                # 如果当天的日志不存在，尝试获取最近的日志文件
                if not os.path.exists(log_file):
                    log_dir = "logs"
                    if os.path.exists(log_dir):
                        log_files = [f for f in os.listdir(log_dir) if (f.startswith("ai_answer_service_") or f == "app.log") and f.endswith(".log")]
                        log_files.sort(reverse=True)  # 按文件名降序排序
                        if log_files:
                            log_file = os.path.join(log_dir, log_files[0])
            
            # 读取日志文件
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    return ''.join(lines[-max_lines:]) if lines else "暂无日志记录"
            else:
                return "日志文件不存在"
        except Exception as e:
            return f"读取日志文件时发生错误: {str(e)}"

# 创建默认的应用日志记录器
app_logger = Logger("ai_answer_service").get_logger()