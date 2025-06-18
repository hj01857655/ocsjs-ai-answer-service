#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务管理脚本
管理模型健康检查、定期任务等服务
"""

import argparse
import sys
import os
import json
import logging
from datetime import datetime

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.append(project_root)
os.chdir(project_root)  # 切换到项目根目录

def setup_logging():
    """设置日志"""
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'{log_dir}/service_manager.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('ServiceManager')

def health_check():
    """执行健康检查"""
    logger = setup_logging()
    logger.info("开始执行健康检查...")

    try:
        from model_health_checker import ModelHealthChecker

        checker = ModelHealthChecker()
        report = checker.run_health_check()

        print(f"🏥 健康检查报告")
        print(f"{'='*50}")
        print(f"🔑 API密钥健康率: {report['api_keys']['health_rate']:.1f}%")
        print(f"🤖 模型健康率: {report['models']['health_rate']:.1f}%")
        print(f"⏱️ 检查耗时: {report['duration']:.1f}秒")

        if report['config_updated']:
            print(f"🔧 配置已自动更新")

        return True

    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return False

def model_test():
    """执行模型测试"""
    logger = setup_logging()
    logger.info("开始执行模型测试...")

    try:
        from model_tester import FastModelTester

        # 读取配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 使用第一个激活的第三方API配置
        third_party_apis = config.get('third_party_apis', [])
        if not third_party_apis:
            raise ValueError("未找到第三方API配置")

        primary_api = None
        for api in third_party_apis:
            if api.get('is_active', True):
                primary_api = api
                break

        if not primary_api:
            primary_api = third_party_apis[0]

        api_base = primary_api['api_base']
        api_keys = primary_api['api_keys']
        models = primary_api['models']

        # 创建测试器
        tester = FastModelTester(api_base, api_keys)

        # 运行测试
        summary = tester.run_fast_test(models, max_workers=8)

        # 保存结果
        results = {
            'summary': summary,
            'stream_models': [{'model': m['model'], 'time': m['result']['time'], 'answer': m['result']['answer']} for m in tester.stream_models],
            'non_stream_models': [{'model': m['model'], 'time': m['result']['time'], 'answer': m['result']['answer']} for m in tester.non_stream_models],
            'failed_models': [{'model': m['model'], 'error': m['result']['error']} for m in tester.failed_models],
            'test_time': datetime.now().isoformat()
        }

        with open('fast_test_results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        logger.info("模型测试完成，结果已保存")
        return True

    except Exception as e:
        logger.error(f"模型测试失败: {e}")
        return False

def start_scheduler():
    """启动定期任务调度器"""
    logger = setup_logging()
    logger.info("启动定期任务调度器...")

    try:
        from scheduler import TaskScheduler

        scheduler = TaskScheduler()
        scheduler.setup_schedules()

        print("🕐 定期任务调度器已启动")
        print("📋 定期任务:")
        print("  • 每日 02:00 - 模型健康检查")
        print("  • 每周日 03:00 - 完整模型测试")
        print("  • 每月1号 04:00 - 清理旧日志")
        print("\n按 Ctrl+C 停止调度器")

        scheduler.run_scheduler()
        return True

    except KeyboardInterrupt:
        logger.info("调度器已停止")
        return True
    except Exception as e:
        logger.error(f"启动调度器失败: {e}")
        return False

def show_status():
    """显示服务状态"""
    print(f"📊 EduBrain AI 服务状态")
    print(f"{'='*50}")

    # 检查配置文件
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        print(f"✅ 配置文件: 正常")
        print(f"🔧 API基础URL: {config['third_party_apis']['api_base']}")
        print(f"🔑 API密钥数量: {len(config['third_party_apis']['api_keys'])}")
        print(f"🤖 配置模型数量: {len(config['third_party_apis']['models'])}")
        print(f"🎯 当前默认模型: {config['third_party_apis']['model']}")

    except Exception as e:
        print(f"❌ 配置文件: 异常 - {e}")

    # 检查日志目录
    if os.path.exists('logs'):
        log_files = [f for f in os.listdir('logs') if f.endswith('.log')]
        print(f"📝 日志文件数量: {len(log_files)}")
    else:
        print(f"📝 日志目录: 不存在")

    # 检查最新测试结果
    if os.path.exists('fast_test_results.json'):
        try:
            with open('fast_test_results.json', 'r', encoding='utf-8') as f:
                results = json.load(f)

            test_time = results.get('test_time', 'Unknown')
            summary = results.get('summary', {})

            print(f"🧪 最新测试时间: {test_time}")
            print(f"📈 模型成功率: {(summary.get('stream_count', 0) + summary.get('non_stream_count', 0)) / (summary.get('stream_count', 0) + summary.get('non_stream_count', 0) + summary.get('failed_count', 1)) * 100:.1f}%")

        except Exception as e:
            print(f"🧪 测试结果: 读取失败 - {e}")
    else:
        print(f"🧪 测试结果: 无记录")

def main():
    parser = argparse.ArgumentParser(description='EduBrain AI 服务管理工具')
    parser.add_argument('command', choices=['health', 'test', 'schedule', 'status'],
                       help='执行的命令')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='详细输出')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    success = False

    if args.command == 'health':
        success = health_check()
    elif args.command == 'test':
        success = model_test()
    elif args.command == 'schedule':
        success = start_scheduler()
    elif args.command == 'status':
        show_status()
        success = True

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
