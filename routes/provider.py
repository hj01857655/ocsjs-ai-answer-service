from flask import Blueprint, render_template, request, jsonify
from models.models import ModelProvider, get_db_session

provider_bp = Blueprint('provider', __name__)

@provider_bp.route('/providers')
def list_providers():
    session = get_db_session()
    providers = session.query(ModelProvider).all()
    default_provider = providers[0].id if providers else None  # 可根据实际逻辑调整
    session.close()
    return render_template(
        'provider.html',
        providers=providers,
        default_provider=default_provider
    )

# --- API: 获取所有供应商 ---
@provider_bp.route('/api/model_providers', methods=['GET'])
def api_get_providers():
    session = get_db_session()
    providers = session.query(ModelProvider).all()
    session.close()
    return jsonify([p.to_dict() for p in providers])

# --- API: 添加供应商 ---
@provider_bp.route('/api/model_providers', methods=['POST'])
def api_add_provider():
    data = request.json
    session = get_db_session()
    provider = ModelProvider(
        name=data.get('name'),
        api_key=data.get('api_key'),
        api_base=data.get('api_base'),
        models=data.get('models'),
        default_model=data.get('default_model'),
        is_active=data.get('is_active', True),
        temperature=data.get('temperature'),
        max_tokens=data.get('max_tokens')
    )
    session.add(provider)
    session.commit()
    result = provider.to_dict()
    session.close()
    return jsonify({'success': True, 'provider': result})

# --- API: 更新供应商 ---
@provider_bp.route('/api/model_providers/<int:provider_id>', methods=['PUT'])
def api_update_provider(provider_id):
    data = request.json
    session = get_db_session()
    provider = session.query(ModelProvider).get(provider_id)
    if not provider:
        session.close()
        return jsonify({'success': False, 'error': 'Provider not found'}), 404
    for field in ['name', 'api_key', 'api_base', 'models', 'default_model', 'is_active', 'temperature', 'max_tokens']:
        if field in data:
            setattr(provider, field, data[field])
    session.commit()
    result = provider.to_dict()
    session.close()
    return jsonify({'success': True, 'provider': result})

# --- API: 删除供应商 ---
@provider_bp.route('/api/model_providers/<int:provider_id>', methods=['DELETE'])
def api_delete_provider(provider_id):
    session = get_db_session()
    provider = session.query(ModelProvider).get(provider_id)
    if not provider:
        session.close()
        return jsonify({'success': False, 'error': 'Provider not found'}), 404
    session.delete(provider)
    session.commit()
    session.close()
    return jsonify({'success': True})
