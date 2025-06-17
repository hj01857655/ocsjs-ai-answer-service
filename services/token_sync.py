import requests
import json
import logging
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CONFIG_PATH = "config.json"
LOG_PATH = "logs/token_sync.log"

# 日志配置
logger = logging.getLogger("token_sync")
logger.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_PATH, encoding='utf-8')
fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
if not logger.hasHandlers():
    logger.addHandler(fh)

def sync_tokens_to_config():
    """
    定时自动获取所有token并写入config.json，添加了重试机制和错误处理
    """
    try:
        # 从config.json读取session
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # 获取session和API基础URL
        session_value = config.get("openai", {}).get("session") or config.get("session")
        if not session_value:
            logger.warning("未配置session，跳过同步")
            return False
            
        API_BASE = config.get("openai", {}).get("api_base", "https://veloera.wei.bi")
        TOKEN_URL = f"{API_BASE}/api/token/?p=0&size=1000"
        
        # 创建带有重试机制的session
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,  # 最多重试3次
            backoff_factor=1,  # 重试间隔时间
            status_forcelist=[429, 500, 502, 503, 504],  # 这些状态码会触发重试
            allowed_methods=["GET"]  # 只对GET请求进行重试
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 设置cookies和headers
        domain = API_BASE.replace('https://', '').replace('http://', '').split('/')[0]
        session.cookies.set('session', session_value, domain=domain, path='/')
        session.headers.update({
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'cache-control': 'no-store',
            'sec-ch-ua': '"Chromium";v="136", "Microsoft Edge";v="136", "Not.A/Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'Content-Type': 'application/json'
        })
        
        # 发送请求获取tokens
        start_time = time.time()
        logger.info(f"开始从 {API_BASE} 获取tokens")
        
        try:
            resp = session.get(TOKEN_URL, timeout=30, verify=False)
            resp.raise_for_status()  # 如果状态码不是200，会抛出异常
        except requests.exceptions.RequestException as e:
            logger.error(f"请求API失败: {str(e)}")
            return False
            
        # 处理响应
        try:
            data = resp.json()
        except json.JSONDecodeError:
            logger.error(f"解析JSON响应失败: {resp.text[:200]}...")
            return False
            
        if "data" not in data or not isinstance(data["data"], list):
            logger.error(f"API响应格式异常: {data}")
            return False
            
        # 提取并验证API密钥
        tokens = data["data"]
        api_keys = []
        
        for t in tokens:
            if not t.get('key'):
                continue
                
            key = t['key']
            if not key.startswith('sk-'):
                key = f"sk-{key}"
                
            # 验证密钥格式
            if len(key) < 20:  # 简单验证密钥长度
                logger.warning(f"跳过无效的API密钥: {key[:10]}...")
                continue
                
            api_keys.append(key)
        
        if not api_keys:
            logger.warning("未获取到任何有效的API Key")
            return False
            
        # 更新配置
        config.setdefault("openai", {})
        config["openai"]["api_key"] = api_keys[0]  # 使用第一个密钥作为主密钥
        config["openai"]["api_keys"] = api_keys
        
        # 备份原配置
        import shutil
        from datetime import datetime
        try:
            backup_path = f"{CONFIG_PATH}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
            shutil.copy2(CONFIG_PATH, backup_path)
            logger.info(f"已备份配置文件到 {backup_path}")
        except Exception as e:
            logger.warning(f"备份配置文件失败: {str(e)}")
        
        # 写入新配置
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            
        elapsed = time.time() - start_time
        logger.info(f"成功同步 {len(api_keys)} 个API Key 到 config.json (耗时: {elapsed:.2f}秒)")
        return True
        
    except Exception as e:
        logger.error(f"同步token到config.json失败: {str(e)}")
        return False