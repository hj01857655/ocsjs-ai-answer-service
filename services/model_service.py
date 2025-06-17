"""
模型服务接口
处理不同供应商的API调用
"""
import os
import json
import logging
import httpx
from typing import Dict, List, Optional, Any, Union
from config.model_providers import provider_manager, ModelProvider

logger = logging.getLogger(__name__)

class ModelResponse:
    """模型响应结果"""
    def __init__(self, 
                 content: str, 
                 provider_id: str, 
                 model: str, 
                 tokens: Dict[str, int] = None,
                 raw_response: Any = None):
        self.content = content
        self.provider_id = provider_id
        self.model = model
        self.tokens = tokens or {}
        self.raw_response = raw_response
    
    def to_dict(self):
        """转换为字典"""
        return {
            'content': self.content,
            'provider_id': self.provider_id,
            'model': self.model,
            'tokens': self.tokens
        }

class ModelService:
    """模型服务接口"""
    
    @staticmethod
    async def generate_response(prompt: str, 
                               provider_id: str = None, 
                               model: str = None,
                               parameters: Dict[str, Any] = None) -> Union[ModelResponse, None]:
        """
        生成模型响应
        :param prompt: 提示文本
        :param provider_id: 供应商ID，如果为None则使用默认供应商
        :param model: 模型名称，如果为None则使用供应商默认模型
        :param parameters: 额外参数
        :return: 模型响应
        """
        # 获取供应商
        provider = None
        if provider_id:
            provider = provider_manager.get_provider(provider_id)
        
        if not provider:
            provider = provider_manager.get_default_provider()
        
        if not provider:
            logger.error("未找到可用的模型供应商")
            return None
        
        # 确定使用的模型
        model_name = model or provider.default_model
        if model_name not in provider.models:
            logger.warning(f"模型 {model_name} 不在供应商 {provider.name} 的支持列表中，使用默认模型")
            model_name = provider.default_model
        
        # 合并参数
        merged_params = provider.parameters.copy()
        if parameters:
            merged_params.update(parameters)
        
        # 根据供应商类型调用不同的API
        try:
            # 支持多类型判断（优先 type 字段，其次 provider_id）
            ptype = getattr(provider, 'type', None) or getattr(provider, 'provider_id', None)
            if ptype == "fal2":
                return await ModelService._call_fal2(provider, model_name, prompt, merged_params)
            elif ptype == "openai":
                return await ModelService._call_openai(provider, model_name, prompt, merged_params)
            elif ptype == "anthropic":
                return await ModelService._call_anthropic(provider, model_name, prompt, merged_params)
            elif ptype == "google":
                return await ModelService._call_google(provider, model_name, prompt, merged_params)
            else:
                logger.error(f"不支持的供应商类型: {ptype}")
                return None
        except Exception as e:
            logger.error(f"调用模型API失败: {str(e)}")
            return None

    @staticmethod
    async def _call_fal2(provider: "ModelProvider", model: str, prompt: str, parameters: dict) -> "ModelResponse":
        """调用Fal2 API"""
        async with httpx.AsyncClient() as client:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {provider.api_key}"
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": parameters.get("temperature", 0.7),
                "max_tokens": parameters.get("max_tokens", 500)
            }
            for key, value in parameters.items():
                if key not in ["temperature", "max_tokens"]:
                    payload[key] = value
            url = provider.api_base.rstrip("/") + "/v1/chat/completions"
            response = await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=60.0
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            tokens = {
                "prompt_tokens": result["usage"].get("prompt_tokens", 0),
                "completion_tokens": result["usage"].get("completion_tokens", 0),
                "total_tokens": result["usage"].get("total_tokens", 0)
            }
            return ModelResponse(
                content=content,
                provider_id=getattr(provider, 'provider_id', None) or getattr(provider, 'id', None),
                model=model,
                tokens=tokens,
                raw_response=result
            )

    
    @staticmethod
    async def _call_openai(provider: ModelProvider, 
                          model: str, 
                          prompt: str, 
                          parameters: Dict[str, Any]) -> ModelResponse:
        """调用OpenAI API"""
        async with httpx.AsyncClient() as client:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {provider.api_key}"
            }
            
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": parameters.get("temperature", 0.7),
                "max_tokens": parameters.get("max_tokens", 500)
            }
            
            # 添加其他可能的参数
            for key, value in parameters.items():
                if key not in ["temperature", "max_tokens"]:
                    payload[key] = value
            
            response = await client.post(
                f"{provider.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            response.raise_for_status()
            result = response.json()
            
            content = result["choices"][0]["message"]["content"]
            tokens = {
                "prompt_tokens": result["usage"]["prompt_tokens"],
                "completion_tokens": result["usage"]["completion_tokens"],
                "total_tokens": result["usage"]["total_tokens"]
            }
            
            return ModelResponse(
                content=content,
                provider_id=provider.provider_id,
                model=model,
                tokens=tokens,
                raw_response=result
            )
    
    @staticmethod
    async def _call_anthropic(provider: ModelProvider, 
                             model: str, 
                             prompt: str, 
                             parameters: Dict[str, Any]) -> ModelResponse:
        """调用Anthropic API"""
        async with httpx.AsyncClient() as client:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": provider.api_key,
                "anthropic-version": "2023-06-01"
            }
            
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": parameters.get("temperature", 0.7),
                "max_tokens": parameters.get("max_tokens", 500)
            }
            
            # 添加其他可能的参数
            for key, value in parameters.items():
                if key not in ["temperature", "max_tokens"]:
                    payload[key] = value
            
            response = await client.post(
                f"{provider.api_base}/v1/messages",
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            response.raise_for_status()
            result = response.json()
            
            content = result["content"][0]["text"]
            tokens = {
                "input_tokens": result.get("usage", {}).get("input_tokens", 0),
                "output_tokens": result.get("usage", {}).get("output_tokens", 0)
            }
            tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
            
            return ModelResponse(
                content=content,
                provider_id=provider.provider_id,
                model=model,
                tokens=tokens,
                raw_response=result
            )
    
    @staticmethod
    async def _call_google(provider: ModelProvider, 
                          model: str, 
                          prompt: str, 
                          parameters: Dict[str, Any]) -> ModelResponse:
        """调用Google API"""
        async with httpx.AsyncClient() as client:
            headers = {
                "Content-Type": "application/json"
            }
            
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": parameters.get("temperature", 0.7),
                    "maxOutputTokens": parameters.get("max_tokens", 500),
                    "topP": parameters.get("top_p", 0.95),
                    "topK": parameters.get("top_k", 40)
                }
            }
            
            # 构建URL，包含API密钥
            url = f"{provider.api_base}/v1beta/models/{model}:generateContent?key={provider.api_key}"
            
            response = await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            response.raise_for_status()
            result = response.json()
            
            content = result["candidates"][0]["content"]["parts"][0]["text"]
            
            # Google API可能不提供token计数
            tokens = {}
            if "usageMetadata" in result:
                tokens = {
                    "prompt_tokens": result["usageMetadata"].get("promptTokenCount", 0),
                    "completion_tokens": result["usageMetadata"].get("candidatesTokenCount", 0),
                    "total_tokens": result["usageMetadata"].get("totalTokenCount", 0)
                }
            
            return ModelResponse(
                content=content,
                provider_id=provider.provider_id,
                model=model,
                tokens=tokens,
                raw_response=result
            )

# 同步版本的模型服务，用于不支持异步的场景
class SyncModelService:
    """同步版本的模型服务"""
    
    @staticmethod
    def generate_response(prompt: str, 
                         provider_id: str = None, 
                         model: str = None,
                         parameters: Dict[str, Any] = None) -> Union[ModelResponse, None]:
        """
        生成模型响应（同步版本）
        :param prompt: 提示文本
        :param provider_id: 供应商ID，如果为None则使用默认供应商
        :param model: 模型名称，如果为None则使用供应商默认模型
        :param parameters: 额外参数
        :return: 模型响应
        """
        # 获取供应商
        provider = None
        if provider_id:
            provider = provider_manager.get_provider(provider_id)
        
        if not provider:
            provider = provider_manager.get_default_provider()
        
        if not provider:
            logger.error("未找到可用的模型供应商")
            return None
        
        # 确定使用的模型
        model_name = model or provider.default_model
        if model_name not in provider.models:
            logger.warning(f"模型 {model_name} 不在供应商 {provider.name} 的支持列表中，使用默认模型")
            model_name = provider.default_model
        
        # 合并参数
        merged_params = provider.parameters.copy()
        if parameters:
            merged_params.update(parameters)
        
        # 根据供应商类型调用不同的API
        try:
            if provider.provider_id == "openai":
                return SyncModelService._call_openai(provider, model_name, prompt, merged_params)
            elif provider.provider_id == "anthropic":
                return SyncModelService._call_anthropic(provider, model_name, prompt, merged_params)
            elif provider.provider_id == "google":
                return SyncModelService._call_google(provider, model_name, prompt, merged_params)
            else:
                logger.error(f"不支持的供应商类型: {provider.provider_id}")
                return None
        except Exception as e:
            logger.error(f"调用模型API失败: {str(e)}")
            return None
    
    @staticmethod
    def _call_openai(provider: ModelProvider, 
                    model: str, 
                    prompt: str, 
                    parameters: Dict[str, Any]) -> ModelResponse:
        """调用OpenAI API（同步版本）"""
        with httpx.Client() as client:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {provider.api_key}"
            }
            
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": parameters.get("temperature", 0.7),
                "max_tokens": parameters.get("max_tokens", 500)
            }
            
            # 添加其他可能的参数
            for key, value in parameters.items():
                if key not in ["temperature", "max_tokens"]:
                    payload[key] = value
            
            response = client.post(
                f"{provider.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            response.raise_for_status()
            result = response.json()
            
            content = result["choices"][0]["message"]["content"]
            tokens = {
                "prompt_tokens": result["usage"]["prompt_tokens"],
                "completion_tokens": result["usage"]["completion_tokens"],
                "total_tokens": result["usage"]["total_tokens"]
            }
            
            return ModelResponse(
                content=content,
                provider_id=provider.provider_id,
                model=model,
                tokens=tokens,
                raw_response=result
            )
    
    @staticmethod
    def _call_anthropic(provider: ModelProvider, 
                       model: str, 
                       prompt: str, 
                       parameters: Dict[str, Any]) -> ModelResponse:
        """调用Anthropic API（同步版本）"""
        with httpx.Client() as client:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": provider.api_key,
                "anthropic-version": "2023-06-01"
            }
            
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": parameters.get("temperature", 0.7),
                "max_tokens": parameters.get("max_tokens", 500)
            }
            
            # 添加其他可能的参数
            for key, value in parameters.items():
                if key not in ["temperature", "max_tokens"]:
                    payload[key] = value
            
            response = client.post(
                f"{provider.api_base}/v1/messages",
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            response.raise_for_status()
            result = response.json()
            
            content = result["content"][0]["text"]
            tokens = {
                "input_tokens": result.get("usage", {}).get("input_tokens", 0),
                "output_tokens": result.get("usage", {}).get("output_tokens", 0)
            }
            tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
            
            return ModelResponse(
                content=content,
                provider_id=provider.provider_id,
                model=model,
                tokens=tokens,
                raw_response=result
            )
    
    @staticmethod
    def _call_google(provider: ModelProvider, 
                    model: str, 
                    prompt: str, 
                    parameters: Dict[str, Any]) -> ModelResponse:
        """调用Google API（同步版本）"""
        with httpx.Client() as client:
            headers = {
                "Content-Type": "application/json"
            }
            
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": parameters.get("temperature", 0.7),
                    "maxOutputTokens": parameters.get("max_tokens", 500),
                    "topP": parameters.get("top_p", 0.95),
                    "topK": parameters.get("top_k", 40)
                }
            }
            
            # 构建URL，包含API密钥
            url = f"{provider.api_base}/v1beta/models/{model}:generateContent?key={provider.api_key}"
            
            response = client.post(
                url,
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            response.raise_for_status()
            result = response.json()
            
            content = result["candidates"][0]["content"]["parts"][0]["text"]
            
            # Google API可能不提供token计数
            tokens = {}
            if "usageMetadata" in result:
                tokens = {
                    "prompt_tokens": result["usageMetadata"].get("promptTokenCount", 0),
                    "completion_tokens": result["usageMetadata"].get("candidatesTokenCount", 0),
                    "total_tokens": result["usageMetadata"].get("totalTokenCount", 0)
                }
            
            return ModelResponse(
                content=content,
                provider_id=provider.provider_id,
                model=model,
                tokens=tokens,
                raw_response=result
            )
