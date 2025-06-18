#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定期任务调度器
管理模型健康检查和其他定期维护任务
"""

import schedule
import time
import logging
import threading
from datetime import datetime
import os
import sys

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.model_health_checker import ModelHealthChecker

class TaskScheduler:
    def __init__(self):
        self.setup_logging()
        self.health_checker = ModelHealthChecker()
        self.running = False

    def setup_logging(self):
        """设置日志"""
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'{log_dir}/scheduler.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('TaskScheduler')

    def daily_health_check(self):
        """每日健康检查任务"""
        self.logger.info("开始执行每日健康检查...")
        try:
            report = self.health_checker.run_health_check(update_config=True)

            # 记录关键指标
            self.logger.info(f"每日健康检查完成:")
            self.logger.info(f"  - API密钥健康率: {report['api_keys']['health_rate']:.1f}%")
            self.logger.info(f"  - 模型健康率: {report['models']['health_rate']:.1f}%")

            # 如果健康率过低，发出警告
            if report['api_keys']['health_rate'] < 50:
                self.logger.warning("⚠️ API密钥健康率过低，请检查密钥状态")

            if report['models']['health_rate'] < 30:
                self.logger.warning("⚠️ 模型健康率过低，请检查API服务状态")

        except Exception as e:
            self.logger.error(f"每日健康检查失败: {e}")

    def weekly_full_check(self):
        """每周完整检查任务"""
        self.logger.info("开始执行每周完整检查...")
        try:
            # 运行完整的模型测试
            from services.fast_concurrent_test import FastModelTester

            # 加载配置
            import json
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 使用第一个激活的第三方API配置
            third_party_apis = config.get('third_party_apis', [])
            if not third_party_apis:
                self.logger.error("未找到第三方API配置")
                return

            primary_api = None
            for api in third_party_apis:
                if api.get('is_active', True):
                    primary_api = api
                    break

            if not primary_api:
                primary_api = third_party_apis[0]

            # 创建测试器并运行测试
            tester = FastModelTester(primary_api['api_base'], primary_api['api_keys'])
            summary = tester.run_fast_test(primary_api['models'], max_workers=5)

            self.logger.info(f"每周完整检查完成:")
            self.logger.info(f"  - 流式模型: {summary['stream_count']} 个")
            self.logger.info(f"  - 非流式模型: {summary['non_stream_count']} 个")
            self.logger.info(f"  - 失败模型: {summary['failed_count']} 个")

            # 保存周报告
            weekly_report = {
                "timestamp": datetime.now().isoformat(),
                "type": "weekly_full_check",
                "summary": summary,
                "stream_models": [{'model': m['model'], 'time': m['result']['time']} for m in tester.stream_models],
                "non_stream_models": [{'model': m['model'], 'time': m['result']['time']} for m in tester.non_stream_models],
                "failed_models": [{'model': m['model'], 'error': m['result']['error']} for m in tester.failed_models]
            }

            report_file = f"logs/weekly_report_{datetime.now().strftime('%Y%m%d')}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(weekly_report, f, ensure_ascii=False, indent=2)

            self.logger.info(f"周报告已保存到 {report_file}")

        except Exception as e:
            self.logger.error(f"每周完整检查失败: {e}")

    def cleanup_old_logs(self):
        """清理旧日志文件"""
        self.logger.info("开始清理旧日志文件...")
        try:
            import glob
            from datetime import datetime, timedelta

            # 清理30天前的日志文件
            cutoff_date = datetime.now() - timedelta(days=30)

            log_files = glob.glob('logs/*.log') + glob.glob('logs/*.json')
            cleaned_count = 0

            for log_file in log_files:
                try:
                    file_time = datetime.fromtimestamp(os.path.getmtime(log_file))
                    if file_time < cutoff_date:
                        os.remove(log_file)
                        cleaned_count += 1
                except Exception as e:
                    self.logger.warning(f"清理日志文件 {log_file} 失败: {e}")

            self.logger.info(f"清理了 {cleaned_count} 个旧日志文件")

        except Exception as e:
            self.logger.error(f"清理旧日志文件失败: {e}")

    def setup_schedules(self):
        """设置定期任务"""
        # 每日凌晨2点执行健康检查
        schedule.every().day.at("02:00").do(self.daily_health_check)

        # 每周日凌晨3点执行完整检查
        schedule.every().sunday.at("03:00").do(self.weekly_full_check)

        # 每月1号凌晨4点清理旧日志
        schedule.every().month.do(self.cleanup_old_logs)

        # 可选：每小时执行一次轻量级检查（仅检查默认模型）
        # schedule.every().hour.do(self.quick_health_check)

        self.logger.info("定期任务调度已设置:")
        self.logger.info("  - 每日 02:00: 健康检查")
        self.logger.info("  - 每周日 03:00: 完整检查")
        self.logger.info("  - 每月1号 04:00: 清理日志")

    def quick_health_check(self):
        """快速健康检查（仅检查默认模型）"""
        try:
            import json
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 使用第一个激活的第三方API配置
            third_party_apis = config.get('third_party_apis', [])
            if not third_party_apis:
                self.logger.error("未找到第三方API配置")
                return

            primary_api = None
            for api in third_party_apis:
                if api.get('is_active', True):
                    primary_api = api
                    break

            if not primary_api:
                primary_api = third_party_apis[0]

            default_model = primary_api['model']
            result = self.health_checker.test_model(default_model)

            if result['success']:
                self.logger.info(f"快速检查: 默认模型 {default_model} 正常")
            else:
                self.logger.warning(f"快速检查: 默认模型 {default_model} 异常 - {result.get('error', 'Unknown')}")

        except Exception as e:
            self.logger.error(f"快速健康检查失败: {e}")

    def run_scheduler(self):
        """运行调度器"""
        self.running = True
        self.logger.info("任务调度器已启动")

        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except KeyboardInterrupt:
                self.logger.info("收到停止信号，正在关闭调度器...")
                self.running = False
            except Exception as e:
                self.logger.error(f"调度器运行异常: {e}")
                time.sleep(60)

        self.logger.info("任务调度器已停止")

    def run_in_background(self):
        """在后台线程中运行调度器"""
        scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
        scheduler_thread.start()
        self.logger.info("任务调度器已在后台启动")
        return scheduler_thread

    def stop(self):
        """停止调度器"""
        self.running = False

def main():
    """主函数"""
    scheduler = TaskScheduler()
    scheduler.setup_schedules()

    print("🕐 任务调度器启动中...")
    print("📋 定期任务:")
    print("  • 每日 02:00 - 模型健康检查")
    print("  • 每周日 03:00 - 完整模型测试")
    print("  • 每月1号 04:00 - 清理旧日志")
    print("\n按 Ctrl+C 停止调度器")

    try:
        scheduler.run_scheduler()
    except KeyboardInterrupt:
        print("\n调度器已停止")

if __name__ == "__main__":
    main()
