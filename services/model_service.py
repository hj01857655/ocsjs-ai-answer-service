"""
模型服务接口
直接使用第三方API代理池，提供统一的模型调用接口
"""
import logging
import httpx
import random
import time
from typing import Dict, Any, Union
from config.api_proxy_pool import get_api_proxy_pool
from config.config import Config
from services.failover_manager import get_failover_manager

logger = logging.getLogger(__name__)

class ModelResponse:
    """模型响应结果"""
    def __init__(self,
                 content: str,
                 proxy_name: str,
                 model: str,
                 tokens: Dict[str, int] = None,
                 raw_response: Any = None):
        self.content = content
        self.proxy_name = proxy_name  # 使用代理名称而不是provider_id
        self.model = model
        self.tokens = tokens or {}
        self.raw_response = raw_response

        # 为了向后兼容，保留provider_id属性
        self.provider_id = proxy_name

    def to_dict(self):
        """转换为字典"""
        return {
            'content': self.content,
            'proxy_name': self.proxy_name,
            'model': self.model,
            'tokens': self.tokens
        }

# 异步版本的ModelService已移除，统一使用SyncModelService

# 所有异步API调用方法已移除

# 同步版本的模型服务，直接使用代理池
class SyncModelService:
    """同步版本的模型服务，直接使用第三方API代理池"""

    @staticmethod
    def generate_response(prompt: str,
                         provider_id: str = None,  # 保留参数以兼容，但忽略
                         model: str = None,
                         parameters: Dict[str, Any] = None) -> Union[ModelResponse, None]:
        """
        生成模型响应（同步版本，支持自动故障转移）
        :param prompt: 提示文本
        :param provider_id: 已废弃参数，保留以兼容旧代码，实际使用代理池自动选择
        :param model: 模型名称，如果为None则使用代理的默认模型
        :param parameters: 额外参数
        :return: 模型响应
        """
        try:
            # 获取代理池
            proxy_pool = get_api_proxy_pool()

            # 获取故障转移管理器
            failover_manager = get_failover_manager()

            # 获取可用的代理列表
            active_proxies = proxy_pool.get_active_proxies()
            if not active_proxies:
                logger.error("没有可用的API代理")
                return None

            # 如果指定了模型，优先选择支持该模型的代理
            candidate_proxies = []
            if model:
                for proxy in active_proxies:
                    if model in proxy.models:
                        candidate_proxies.append(proxy)

            # 如果没有找到支持指定模型的代理，使用所有激活的代理
            if not candidate_proxies:
                candidate_proxies = active_proxies

            # 过滤掉不健康的代理（如果启用了故障转移）
            if failover_manager.is_enabled():
                healthy_proxies = []
                for proxy in candidate_proxies:
                    if failover_manager.is_proxy_healthy(proxy.name):
                        healthy_proxies.append(proxy)
                    else:
                        logger.info(f"跳过不健康的代理: {proxy.name}")

                if healthy_proxies:
                    candidate_proxies = healthy_proxies
                else:
                    logger.warning("所有代理都不健康，将尝试所有代理")

            # 按优先级排序
            candidate_proxies.sort(key=lambda x: x.priority)

            # 尝试每个代理，实现自动故障转移
            last_error = None
            for i, proxy in enumerate(candidate_proxies):
                try:
                    # 确定使用的模型
                    model_name = model or proxy.model
                    if not model_name and proxy.models:
                        model_name = proxy.models[0]

                    logger.info(f"尝试代理 {i+1}/{len(candidate_proxies)}: {proxy.name}")
                    logger.info(f"使用模型: {model_name}")
                    logger.info(f"API地址: {proxy.api_base}")

                    # 获取API密钥
                    api_key = proxy.current_api_key
                    if not api_key:
                        logger.warning(f"代理 {proxy.name} 没有可用的API密钥，跳过")
                        continue

                    # 合并参数
                    merged_params = {
                        "temperature": Config.TEMPERATURE,
                        "max_tokens": Config.MAX_TOKENS
                    }
                    if parameters:
                        merged_params.update(parameters)

                    # 记录开始时间
                    start_time = time.time()

                    # 调用API
                    response = SyncModelService._call_proxy_api(
                        proxy, model_name, prompt, merged_params
                    )

                    # 计算响应时间
                    response_time = (time.time() - start_time) * 1000  # 转换为毫秒

                    if response:
                        # 记录成功（包含响应时间）
                        failover_manager.record_success(proxy.name, response_time)
                        logger.info(f"代理 {proxy.name} 调用成功，响应时间: {response_time:.2f}ms")
                        return response
                    else:
                        # 记录失败
                        failover_manager.record_failure(proxy.name, "返回空响应")
                        logger.warning(f"代理 {proxy.name} 返回空响应，尝试下一个代理")

                except Exception as e:
                    last_error = e
                    # 记录失败
                    failover_manager.record_failure(proxy.name, str(e))
                    logger.warning(f"代理 {proxy.name} 调用失败: {str(e)}")

                    # 如果不是最后一个代理，继续尝试下一个
                    if i < len(candidate_proxies) - 1:
                        logger.info(f"自动切换到下一个代理...")
                        continue
                    else:
                        logger.error(f"所有代理都已尝试，最后一个错误: {str(e)}")

            # 所有代理都失败了
            logger.error("所有可用代理都调用失败")
            if last_error:
                raise last_error
            return None

        except Exception as e:
            logger.error(f"代理池调用失败: {str(e)}")
            return None

    @staticmethod
    def _call_proxy_api(proxy, model: str, prompt: str, parameters: Dict[str, Any]) -> ModelResponse:
        """调用代理API（所有代理都使用OpenAI兼容格式，支持重试和错误处理）"""
        max_retries = 2
        retry_count = 0

        while retry_count <= max_retries:
            try:
                with httpx.Client(verify=False) as client:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {proxy.current_api_key}"
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

                    # 构建API URL，确保正确的路径
                    api_base = proxy.api_base.rstrip('/')

                    # 检查API base是否已经包含完整路径
                    if '/chat/completions' in api_base:
                        # 如果已经包含完整路径，直接使用
                        url = api_base
                    elif api_base.endswith('/v1'):
                        # 如果已经以/v1结尾，直接添加/chat/completions
                        url = f"{api_base}/chat/completions"
                    else:
                        # 标准OpenAI兼容API，添加/v1/chat/completions
                        url = f"{api_base}/v1/chat/completions"

                    if retry_count == 0:
                        logger.info(f"调用代理API: {url}")
                        logger.info(f"使用模型: {model}")
                        logger.info(f"代理名称: {proxy.name}")
                    else:
                        logger.info(f"重试第 {retry_count} 次调用代理 {proxy.name}")

                    response = client.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=30.0  # 减少超时时间以便快速故障转移
                    )

                    # 检查HTTP状态码
                    if response.status_code == 401:
                        logger.error(f"代理 {proxy.name} 认证失败 (401)")
                        raise Exception(f"API密钥无效或已过期")
                    elif response.status_code == 403:
                        logger.error(f"代理 {proxy.name} 访问被拒绝 (403)")
                        raise Exception(f"API密钥权限不足")
                    elif response.status_code == 429:
                        logger.warning(f"代理 {proxy.name} 请求频率限制 (429)")
                        if retry_count < max_retries:
                            import time
                            time.sleep(2 ** retry_count)  # 指数退避
                            retry_count += 1
                            continue
                        else:
                            raise Exception(f"请求频率限制，已达到最大重试次数")
                    elif response.status_code >= 500:
                        logger.warning(f"代理 {proxy.name} 服务器错误 ({response.status_code})")
                        if retry_count < max_retries:
                            retry_count += 1
                            continue
                        else:
                            raise Exception(f"服务器错误 {response.status_code}")

                    response.raise_for_status()
                    result = response.json()

                    # 验证响应格式
                    if "choices" not in result or not result["choices"]:
                        raise Exception("API响应格式无效：缺少choices字段")

                    if "message" not in result["choices"][0]:
                        raise Exception("API响应格式无效：缺少message字段")

                    content = result["choices"][0]["message"]["content"]
                    if not content or content.strip() == "":
                        raise Exception("API返回空内容")

                    tokens = {
                        "prompt_tokens": result.get("usage", {}).get("prompt_tokens", 0),
                        "completion_tokens": result.get("usage", {}).get("completion_tokens", 0),
                        "total_tokens": result.get("usage", {}).get("total_tokens", 0)
                    }

                    logger.info(f"代理 {proxy.name} 调用成功，返回内容长度: {len(content)}")
                    return ModelResponse(
                        content=content,
                        proxy_name=proxy.name,
                        model=model,
                        tokens=tokens,
                        raw_response=result
                    )

            except httpx.TimeoutException:
                logger.warning(f"代理 {proxy.name} 请求超时")
                if retry_count < max_retries:
                    retry_count += 1
                    continue
                else:
                    raise Exception("请求超时，已达到最大重试次数")
            except httpx.ConnectError:
                logger.error(f"代理 {proxy.name} 连接失败")
                raise Exception("无法连接到API服务器")
            except Exception as e:
                if retry_count < max_retries and "服务器错误" in str(e):
                    retry_count += 1
                    continue
                else:
                    raise e

# 所有旧的API调用方法已移除，统一使用 _call_proxy_api 方法
