#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代理池管理路由
提供代理的增删改查、健康检查、模型发现等功能
"""

from flask import Blueprint, request, jsonify
import json
import requests
import time
import threading
from datetime import datetime
from utils import login_required, admin_required
from utils.logger import app_logger as logger
from config.api_proxy_pool import get_api_proxy_pool

proxy_management_bp = Blueprint('proxy_management', __name__)

# 全局变量用于健康检查
health_check_results = {}
health_check_lock = threading.Lock()

@proxy_management_bp.route('/api/proxy/add', methods=['POST'])
@login_required
@admin_required
def add_proxy():
    """添加新代理"""
    try:
        data = request.get_json()

        # 验证必填字段
        required_fields = ['name', 'api_base', 'api_keys', 'model', 'models']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'message': f'缺少必填字段: {field}'
                }), 400

        # 验证API密钥格式
        if not isinstance(data['api_keys'], list) or len(data['api_keys']) == 0:
            return jsonify({
                'success': False,
                'message': 'api_keys必须是非空数组'
            }), 400

        # 验证模型列表格式
        if not isinstance(data['models'], list) or len(data['models']) == 0:
            return jsonify({
                'success': False,
                'message': 'models必须是非空数组'
            }), 400

        # 读取当前配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 检查代理名称是否已存在
        existing_names = [proxy['name'] for proxy in config.get('third_party_apis', [])]
        if data['name'] in existing_names:
            return jsonify({
                'success': False,
                'message': f'代理名称 "{data["name"]}" 已存在'
            }), 400

        # 构建新代理配置
        new_proxy = {
            'name': data['name'],
            'api_base': data['api_base'].rstrip('/'),
            'api_keys': data['api_keys'],
            'model': data['model'],
            'models': data['models'],
            'is_active': data.get('is_active', True),
            'priority': data.get('priority', len(config.get('third_party_apis', [])) + 1)
        }

        # 添加到配置
        if 'third_party_apis' not in config:
            config['third_party_apis'] = []
        config['third_party_apis'].append(new_proxy)

        # 保存配置
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # 重新加载代理池
        get_api_proxy_pool(reload=True)

        logger.info(f"添加新代理成功: {data['name']}")
        return jsonify({
            'success': True,
            'message': f'代理 "{data["name"]}" 添加成功'
        })

    except Exception as e:
        logger.error(f"添加代理失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'添加代理失败: {str(e)}'
        }), 500

@proxy_management_bp.route('/api/proxy/update', methods=['POST'])
@login_required
@admin_required
def update_proxy():
    """更新代理配置"""
    try:
        data = request.get_json()

        if 'name' not in data:
            return jsonify({
                'success': False,
                'message': '缺少代理名称'
            }), 400

        # 读取当前配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 查找要更新的代理
        proxy_found = False
        for i, proxy in enumerate(config.get('third_party_apis', [])):
            if proxy['name'] == data['name']:
                # 更新代理配置
                for key, value in data.items():
                    if key != 'name':  # 不允许修改名称
                        proxy[key] = value
                proxy_found = True
                break

        if not proxy_found:
            return jsonify({
                'success': False,
                'message': f'未找到代理: {data["name"]}'
            }), 404

        # 保存配置
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # 重新加载代理池
        get_api_proxy_pool(reload=True)

        logger.info(f"更新代理成功: {data['name']}")
        return jsonify({
            'success': True,
            'message': f'代理 "{data["name"]}" 更新成功'
        })

    except Exception as e:
        logger.error(f"更新代理失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'更新代理失败: {str(e)}'
        }), 500

@proxy_management_bp.route('/api/proxy/delete', methods=['POST'])
@login_required
@admin_required
def delete_proxy():
    """删除代理"""
    try:
        data = request.get_json()

        if 'name' not in data:
            return jsonify({
                'success': False,
                'message': '缺少代理名称'
            }), 400

        # 读取当前配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 查找并删除代理
        original_count = len(config.get('third_party_apis', []))
        config['third_party_apis'] = [
            proxy for proxy in config.get('third_party_apis', [])
            if proxy['name'] != data['name']
        ]

        if len(config['third_party_apis']) == original_count:
            return jsonify({
                'success': False,
                'message': f'未找到代理: {data["name"]}'
            }), 404

        # 保存配置
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # 重新加载代理池
        get_api_proxy_pool(reload=True)

        logger.info(f"删除代理成功: {data['name']}")
        return jsonify({
            'success': True,
            'message': f'代理 "{data["name"]}" 删除成功'
        })

    except Exception as e:
        logger.error(f"删除代理失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'删除代理失败: {str(e)}'
        }), 500

@proxy_management_bp.route('/api/proxy/test', methods=['POST'])
@login_required
def test_proxy():
    """测试代理连接"""
    try:
        data = request.get_json()

        required_fields = ['api_base', 'api_key']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'message': f'缺少必填字段: {field}'
                }), 400

        api_base = data['api_base'].rstrip('/')
        api_key = data['api_key']
        auto_fill = data.get('auto_fill', False)  # 是否自动填充信息

        # 测试连接
        test_url = f"{api_base}/v1/models"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        start_time = time.time()
        try:
            response = requests.get(test_url, headers=headers, timeout=10, verify=False)
            response_time = round((time.time() - start_time) * 1000, 2)

            if response.status_code == 200:
                result = {
                    'success': True,
                    'message': '代理连接测试成功',
                    'response_time': response_time,
                    'status_code': response.status_code
                }

                # 如果需要自动填充，获取模型列表和建议信息
                if auto_fill:
                    try:
                        response_data = response.json()
                        if 'data' in response_data and isinstance(response_data['data'], list):
                            models = []
                            for model in response_data['data']:
                                if isinstance(model, dict) and 'id' in model:
                                    models.append(model['id'])

                            if models:
                                result['models'] = models
                                result['default_model'] = auto_select_default_model(models)
                                result['suggested_name'] = auto_generate_proxy_name(api_base, models)
                                result['message'] += f'，发现 {len(models)} 个可用模型'
                    except Exception as e:
                        logger.warning(f"获取模型信息失败: {str(e)}")
                        # 测试成功但获取模型失败，不影响主要结果

                return jsonify(result)
            else:
                result = {
                    'success': False,
                    'message': f'代理连接测试失败: HTTP {response.status_code}',
                    'response_time': response_time,
                    'status_code': response.status_code
                }

                # 即使测试失败，如果启用自动填充，也尝试生成建议名称
                if auto_fill:
                    try:
                        suggested_name = auto_generate_proxy_name(api_base, [])
                        result['suggested_name'] = suggested_name
                        result['message'] += f'，建议代理名称: {suggested_name}'
                    except Exception as e:
                        logger.warning(f"生成建议名称失败: {str(e)}")

                return jsonify(result)
        except requests.exceptions.Timeout:
            return jsonify({
                'success': False,
                'message': '代理连接测试超时',
                'response_time': 10000
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'代理连接测试失败: {str(e)}',
                'response_time': round((time.time() - start_time) * 1000, 2)
            })

    except Exception as e:
        logger.error(f"测试代理失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'测试代理失败: {str(e)}'
        }), 500

@proxy_management_bp.route('/api/proxy/discover-models', methods=['POST'])
@login_required
def discover_models():
    """自动发现代理支持的模型"""
    try:
        data = request.get_json()

        required_fields = ['api_base', 'api_key']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'message': f'缺少必填字段: {field}'
                }), 400

        api_base = data['api_base'].rstrip('/')
        api_key = data['api_key']

        # 调用模型列表API
        models_url = f"{api_base}/v1/models"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.get(models_url, headers=headers, timeout=15, verify=False)

            if response.status_code == 200:
                response_data = response.json()
                if 'data' in response_data and isinstance(response_data['data'], list):
                    models = []
                    for model in response_data['data']:
                        if isinstance(model, dict) and 'id' in model:
                            models.append(model['id'])

                    if models:
                        # 自动选择默认模型
                        default_model = auto_select_default_model(models)

                        # 尝试自动生成代理名称
                        suggested_name = auto_generate_proxy_name(api_base, models)

                        return jsonify({
                            'success': True,
                            'message': f'成功发现 {len(models)} 个模型',
                            'models': models,
                            'default_model': default_model,
                            'suggested_name': suggested_name
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'message': '未发现任何可用模型'
                        })
                else:
                    # API返回格式不正确，但仍尝试生成建议名称
                    suggested_name = auto_generate_proxy_name(api_base, [])
                    return jsonify({
                        'success': False,
                        'message': 'API返回格式不正确',
                        'suggested_name': suggested_name
                    })
            else:
                # 获取模型列表失败，但仍尝试生成建议名称
                suggested_name = auto_generate_proxy_name(api_base, [])
                return jsonify({
                    'success': False,
                    'message': f'获取模型列表失败: HTTP {response.status_code}',
                    'suggested_name': suggested_name
                })

        except requests.exceptions.Timeout:
            # 超时也尝试生成建议名称
            suggested_name = auto_generate_proxy_name(api_base, [])
            return jsonify({
                'success': False,
                'message': '获取模型列表超时',
                'suggested_name': suggested_name
            })
        except Exception as e:
            # 异常也尝试生成建议名称
            suggested_name = auto_generate_proxy_name(api_base, [])
            return jsonify({
                'success': False,
                'message': f'获取模型列表失败: {str(e)}',
                'suggested_name': suggested_name
            })

    except Exception as e:
        logger.error(f"发现模型失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'发现模型失败: {str(e)}'
        }), 500

def auto_select_default_model(models):
    """自动选择默认模型"""
    # 优先级列表：从最优到次优
    priority_models = [
        # GPT系列
        'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo',
        # Claude系列
        'claude-3-5-sonnet-20241022', 'claude-3-5-sonnet', 'claude-3-opus', 'claude-3-sonnet', 'claude-3-haiku',
        # Gemini系列
        'gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-pro',
        # 其他流行模型
        'llama-3.1-405b', 'llama-3.1-70b', 'llama-3.1-8b',
        'qwen-max', 'qwen-plus', 'qwen-turbo',
        'deepseek-chat', 'deepseek-coder',
        'yi-large', 'yi-medium',
        'moonshot-v1-128k', 'moonshot-v1-32k', 'moonshot-v1-8k'
    ]

    # 按优先级查找
    for priority_model in priority_models:
        for model in models:
            if priority_model.lower() in model.lower():
                return model

    # 如果没有找到优先模型，选择第一个包含常见关键词的模型
    common_keywords = ['gpt', 'claude', 'gemini', 'llama', 'qwen', 'chat', 'turbo']
    for keyword in common_keywords:
        for model in models:
            if keyword.lower() in model.lower():
                return model

    # 最后返回第一个模型
    return models[0] if models else ''

def auto_generate_proxy_name(api_base, models):
    """自动生成代理名称"""
    try:
        from urllib.parse import urlparse

        # 解析URL获取域名
        parsed_url = urlparse(api_base)
        domain = parsed_url.netloc.lower()

        # 移除常见前缀
        domain = domain.replace('api.', '').replace('www.', '')

        # 根据域名特征生成名称
        if 'openai' in domain:
            return 'OpenAI API'
        elif 'anthropic' in domain or 'claude' in domain:
            return 'Claude API'
        elif 'google' in domain or 'gemini' in domain:
            return 'Gemini API'
        elif 'deepseek' in domain:
            return 'DeepSeek API'
        elif 'moonshot' in domain:
            return 'Moonshot API'
        elif 'qwen' in domain or 'alibaba' in domain:
            return 'Qwen API'
        elif 'yi' in domain or '01.ai' in domain:
            return 'Yi API'
        elif 'baidu' in domain:
            return 'Baidu API'
        elif 'tencent' in domain:
            return 'Tencent API'
        elif 'hunyuan' in domain:
            return 'Hunyuan API'

        # 根据模型名称推断
        if models:
            first_model = models[0].lower()
            if 'gpt' in first_model:
                return 'GPT API'
            elif 'claude' in first_model:
                return 'Claude API'
            elif 'gemini' in first_model:
                return 'Gemini API'
            elif 'llama' in first_model:
                return 'Llama API'
            elif 'qwen' in first_model:
                return 'Qwen API'
            elif 'deepseek' in first_model:
                return 'DeepSeek API'
            elif 'yi' in first_model:
                return 'Yi API'

        # 使用域名的主要部分
        domain_parts = domain.split('.')
        if len(domain_parts) >= 2:
            main_domain = domain_parts[-2]  # 获取主域名部分
            return f"{main_domain.capitalize()} API"

        # 默认名称
        return f"第三方API ({domain})"

    except Exception as e:
        logger.warning(f"自动生成代理名称失败: {str(e)}")
        return "第三方API"

@proxy_management_bp.route('/api/proxy/health-check', methods=['GET'])
@login_required
def get_health_status():
    """获取所有代理的健康状态"""
    try:
        with health_check_lock:
            return jsonify({
                'success': True,
                'health_status': health_check_results.copy()
            })
    except Exception as e:
        logger.error(f"获取健康状态失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取健康状态失败: {str(e)}'
        }), 500

def check_proxy_health(proxy_name, api_base, api_key):
    """检查单个代理的健康状态"""
    try:
        test_url = f"{api_base.rstrip('/')}/v1/models"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        start_time = time.time()
        response = requests.get(test_url, headers=headers, timeout=10, verify=False)
        response_time = round((time.time() - start_time) * 1000, 2)

        with health_check_lock:
            health_check_results[proxy_name] = {
                'status': 'online' if response.status_code == 200 else 'error',
                'response_time': response_time,
                'status_code': response.status_code,
                'last_check': datetime.now().isoformat(),
                'error_message': None if response.status_code == 200 else f'HTTP {response.status_code}'
            }

    except requests.exceptions.Timeout:
        with health_check_lock:
            health_check_results[proxy_name] = {
                'status': 'timeout',
                'response_time': 10000,
                'status_code': None,
                'last_check': datetime.now().isoformat(),
                'error_message': '连接超时'
            }
    except Exception as e:
        with health_check_lock:
            health_check_results[proxy_name] = {
                'status': 'offline',
                'response_time': None,
                'status_code': None,
                'last_check': datetime.now().isoformat(),
                'error_message': str(e)
            }

def run_health_checks():
    """运行所有代理的健康检查"""
    try:
        # 读取配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        proxies = config.get('third_party_apis', [])
        threads = []

        for proxy in proxies:
            if proxy.get('is_active', True) and proxy.get('api_keys'):
                # 使用第一个API密钥进行健康检查
                api_key = proxy['api_keys'][0] if isinstance(proxy['api_keys'], list) else proxy['api_keys']
                thread = threading.Thread(
                    target=check_proxy_health,
                    args=(proxy['name'], proxy['api_base'], api_key)
                )
                thread.daemon = True
                thread.start()
                threads.append(thread)

        # 等待所有检查完成
        for thread in threads:
            thread.join(timeout=15)

    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}")

# 健康检查定时器
health_check_timer = None

def start_health_check_timer():
    """启动健康检查定时器"""
    global health_check_timer

    def health_check_loop():
        while True:
            try:
                run_health_checks()
                time.sleep(60)  # 每60秒检查一次
            except Exception as e:
                logger.error(f"健康检查循环异常: {str(e)}")
                time.sleep(60)

    if health_check_timer is None or not health_check_timer.is_alive():
        health_check_timer = threading.Thread(target=health_check_loop, daemon=True)
        health_check_timer.start()
        logger.info("健康检查定时器已启动")

@proxy_management_bp.route('/api/proxy/get-full-info', methods=['POST'])
@login_required
@admin_required
def get_proxy_full_info():
    """获取代理的完整信息（包含未掩码的API密钥）- 仅用于编辑"""
    try:
        data = request.get_json()

        if 'name' not in data:
            return jsonify({
                'success': False,
                'message': '缺少代理名称'
            }), 400

        # 读取配置文件获取完整信息
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 查找代理
        for proxy in config.get('third_party_apis', []):
            if proxy['name'] == data['name']:
                return jsonify({
                    'success': True,
                    'proxy': {
                        'name': proxy['name'],
                        'api_base': proxy['api_base'],
                        'keys': proxy.get('api_keys', []),  # 完整的API密钥
                        'default_model': proxy.get('model', ''),
                        'models': proxy.get('models', []),
                        'is_active': proxy.get('is_active', True),
                        'priority': proxy.get('priority', 1)
                    }
                })

        return jsonify({
            'success': False,
            'message': f'未找到代理: {data["name"]}'
        }), 404

    except Exception as e:
        logger.error(f"获取代理完整信息失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取代理完整信息失败: {str(e)}'
        }), 500

@proxy_management_bp.route('/api/proxy/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_proxy_status():
    """切换代理的启用/禁用状态"""
    try:
        data = request.get_json()

        if 'name' not in data:
            return jsonify({
                'success': False,
                'message': '缺少代理名称'
            }), 400

        # 读取当前配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 查找并切换代理状态
        proxy_found = False
        for proxy in config.get('third_party_apis', []):
            if proxy['name'] == data['name']:
                proxy['is_active'] = not proxy.get('is_active', True)
                new_status = '启用' if proxy['is_active'] else '禁用'
                proxy_found = True
                break

        if not proxy_found:
            return jsonify({
                'success': False,
                'message': f'未找到代理: {data["name"]}'
            }), 404

        # 保存配置
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # 重新加载代理池
        get_api_proxy_pool(reload=True)

        logger.info(f"切换代理状态成功: {data['name']} -> {new_status}")
        return jsonify({
            'success': True,
            'message': f'代理 "{data["name"]}" 已{new_status}',
            'is_active': proxy['is_active']
        })

    except Exception as e:
        logger.error(f"切换代理状态失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'切换代理状态失败: {str(e)}'
        }), 500
