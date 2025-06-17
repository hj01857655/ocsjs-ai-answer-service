from flask import Blueprint, jsonify, request
import os
import json

model_providers_bp = Blueprint('model_providers', __name__, url_prefix='/api/model_providers')

# 配置文件路径，可根据实际情况调整
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'model_providers.json')

@model_providers_bp.route('/', methods=['GET'])
def get_model_providers():
    """
    获取所有模型提供者信息
    """
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@model_providers_bp.route('/', methods=['POST'])
def update_model_providers():
    """
    更新模型提供者信息
    """
    try:
        data = request.get_json(force=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
