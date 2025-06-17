"""
模型供应商配置模块
支持多个AI模型提供商的配置和管理
"""
import os
import json
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class ModelProvider:
    """模型供应商基类"""
    def __init__(self, 
                 provider_id: str, 
                 name: str, 
                 api_key: str, 
                 api_base: str,
                 models: List[str],
                 default_model: str,
                 is_active: bool = True,
                 parameters: Dict[str, Any] = None):
        self.provider_id = provider_id
        self.name = name
        self.api_key = api_key
        self.api_base = api_base
        self.models = models
        self.default_model = default_model
        self.is_active = is_active
        self.parameters = parameters or {}
    
    def to_dict(self):
        """转换为字典"""
        return {
            'provider_id': self.provider_id,
            'name': self.name,
            'api_key': self._mask_api_key(),
            'api_base': self.api_base,
            'models': self.models,
            'default_model': self.default_model,
            'is_active': self.is_active,
            'parameters': self.parameters
        }
    
    def _mask_api_key(self):
        """掩码API密钥，只显示前4位和后4位"""
        if not self.api_key or len(self.api_key) < 8:
            return "****"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"

class ProviderManager:
    """模型供应商管理器"""
    def __init__(self):
        self.providers: Dict[str, ModelProvider] = {}
        self.default_provider_id = None
    
    def add_provider(self, provider_id: str = None, name: str = None, api_key: str = None, 
                   api_base: str = None, models: List[str] = None, default_model: str = None, 
                   is_active: bool = True, parameters: Dict[str, Any] = None, provider: ModelProvider = None):
        """添加供应商
        
        可以直接传入ModelProvider对象，或者传入各个参数来创建新的供应商
        
        Args:
            provider_id: 供应商ID
            name: 供应商名称
            api_key: API密钥
            api_base: API基础URL
            models: 可用模型列表
            default_model: 默认模型
            is_active: 是否激活
            parameters: 参数设置
            provider: ModelProvider对象
        """
        # 如果传入了ModelProvider对象，直接使用
        if provider is not None:
            self.providers[provider.provider_id] = provider
        # 否则创建新的ModelProvider对象
        elif provider_id is not None:
            provider = ModelProvider(
                provider_id=provider_id,
                name=name or provider_id,
                api_key=api_key or '',
                api_base=api_base or '',
                models=models or [],
                default_model=default_model or (models[0] if models else ''),
                is_active=is_active,
                parameters=parameters or {}
            )
            self.providers[provider_id] = provider
        else:
            raise ValueError("必须提供 provider_id 或 provider 参数")
            
        # 如果是第一个添加的供应商，设为默认
        if self.default_provider_id is None:
            self.default_provider_id = provider.provider_id
            
        return provider
    
    def get_provider(self, provider_id: str) -> Optional[ModelProvider]:
        """获取指定ID的供应商"""
        return self.providers.get(provider_id)
    
    def get_default_provider(self) -> Optional[ModelProvider]:
        """获取默认供应商"""
        if self.default_provider_id:
            return self.providers.get(self.default_provider_id)
        return None
    
    def set_default_provider(self, provider_id: str) -> bool:
        """设置默认供应商"""
        if provider_id in self.providers:
            self.default_provider_id = provider_id
            return True
        return False
    
    def get_active_providers(self) -> List[ModelProvider]:
        """获取所有激活的供应商"""
        return [p for p in self.providers.values() if p.is_active]
    
    def get_all_providers(self) -> List[ModelProvider]:
        """获取所有供应商，无论是否激活"""
        return list(self.providers.values())
        
    def get_default_provider_id(self) -> Optional[str]:
        """获取默认供应商ID"""
        return self.default_provider_id
    
    def load_from_config(self, config_data: Dict):
        """从配置数据加载供应商"""
        providers_config = config_data.get('model_providers', [])
        default_provider = config_data.get('default_provider')
        
        for provider_config in providers_config:
            provider = ModelProvider(
                provider_id=provider_config.get('provider_id'),
                name=provider_config.get('name'),
                api_key=provider_config.get('api_key', ''),
                api_base=provider_config.get('api_base', ''),
                models=provider_config.get('models', []),
                default_model=provider_config.get('default_model', ''),
                is_active=provider_config.get('is_active', True),
                parameters=provider_config.get('parameters', {})
            )
            self.add_provider(provider)
        
        if default_provider and default_provider in self.providers:
            self.default_provider_id = default_provider
    
    def save_to_config(self) -> Dict:
        """保存供应商配置到字典"""
        providers_config = []
        for provider in self.providers.values():
            # 不保存API密钥的掩码版本
            provider_dict = provider.to_dict()
            provider_dict['api_key'] = provider.api_key  # 使用原始API密钥
            providers_config.append(provider_dict)
        
        return {
            'model_providers': providers_config,
            'default_provider': self.default_provider_id
        }

# 创建全局供应商管理器实例
provider_manager = ProviderManager()

def load_providers_from_file(config_file_path: str):
    """从配置文件加载供应商"""
    try:
        if os.path.exists(config_file_path):
            with open(config_file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                provider_manager.load_from_config(config_data)
                logger.info(f"已加载 {len(provider_manager.providers)} 个模型供应商")
        else:
            logger.warning(f"模型供应商配置文件不存在: {config_file_path}")
    except Exception as e:
        logger.error(f"加载模型供应商配置失败: {str(e)}")

def save_providers_to_file(config_file_path: str):
    """保存供应商到配置文件"""
    try:
        config_dir = os.path.dirname(config_file_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        config_data = provider_manager.save_to_config()
        with open(config_file_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        logger.info(f"已保存 {len(provider_manager.providers)} 个模型供应商到配置文件")
        return True
    except Exception as e:
        logger.error(f"保存模型供应商配置失败: {str(e)}")
        return False

def initialize_default_providers():
    """初始化默认供应商"""
    from config.config import Config
    
    # 添加OpenAI供应商
    openai_provider = ModelProvider(
        provider_id="openai",
        name="OpenAI",
        api_key=Config.OPENAI_API_KEY or "",
        api_base=Config.OPENAI_API_BASE or "https://api.openai.com/v1",
        models=Config.OPENAI_MODELS or ["gpt-4o", "gpt-4.1-mini", "gpt-4.1-nano"],
        default_model=Config.OPENAI_MODEL or "gpt-4.1-mini",
        parameters={
            "temperature": Config.OPENAI_TEMPERATURE,
            "max_tokens": Config.OPENAI_MAX_TOKENS
        }
    )
    provider_manager.add_provider(openai_provider)
    
    # 添加Anthropic供应商（如果配置了）
    if hasattr(Config, 'ANTHROPIC_API_KEY') and Config.ANTHROPIC_API_KEY:
        anthropic_provider = ModelProvider(
            provider_id="anthropic",
            name="Anthropic",
            api_key=Config.ANTHROPIC_API_KEY,
            api_base=getattr(Config, 'ANTHROPIC_API_BASE', "https://api.anthropic.com"),
            models=getattr(Config, 'ANTHROPIC_MODELS', ["claude-3-opus-20240229", "claude-3-sonnet-20240229"]),
            default_model=getattr(Config, 'ANTHROPIC_MODEL', "claude-3-sonnet-20240229"),
            parameters={
                "temperature": getattr(Config, 'ANTHROPIC_TEMPERATURE', 0.7),
                "max_tokens": getattr(Config, 'ANTHROPIC_MAX_TOKENS', 500)
            }
        )
        provider_manager.add_provider(anthropic_provider)
    
    # 添加Google供应商（如果配置了）
    if hasattr(Config, 'GOOGLE_API_KEY') and Config.GOOGLE_API_KEY:
        google_provider = ModelProvider(
            provider_id="google",
            name="Google AI",
            api_key=Config.GOOGLE_API_KEY,
            api_base=getattr(Config, 'GOOGLE_API_BASE', "https://generativelanguage.googleapis.com"),
            models=getattr(Config, 'GOOGLE_MODELS', ["gemini-pro", "gemini-ultra"]),
            default_model=getattr(Config, 'GOOGLE_MODEL', "gemini-pro"),
            parameters={
                "temperature": getattr(Config, 'GOOGLE_TEMPERATURE', 0.7),
                "max_tokens": getattr(Config, 'GOOGLE_MAX_TOKENS', 500)
            }
        )
        provider_manager.add_provider(google_provider)
