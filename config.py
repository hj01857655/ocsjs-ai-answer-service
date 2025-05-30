# -*- coding: utf-8 -*-
"""
配置文件
"""
import os
import json


# 加载JSON配置文件
def load_config():
    config_file = os.path.join(os.path.dirname(__file__), 'config.json')
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"读取配置文件出错: {str(e)}")
    return {}

# 全局配置
_config = load_config()

# 基础配置
class Config:
    # 服务配置
    HOST = _config.get('service', {}).get('host', "0.0.0.0")
    PORT = int(_config.get('service', {}).get('port', 5000))
    DEBUG = _config.get('service', {}).get('debug', True)
    SSL_CERT_FILE = _config.get('SSL_CERT_FILE')
    
    # 安全配置
    SECRET_KEY = _config.get('security', {}).get('secret_key', os.urandom(24))
    
    # OpenAI配置
    OPENAI_API_KEY = _config.get('openai', {}).get('api_key')
    OPENAI_MODEL = _config.get('openai', {}).get('model', "gpt-4.1-mini")
    OPENAI_MODELS = _config.get('openai', {}).get('models', ["gpt-4o", "gpt-4.1-mini", "gpt-4.1-nano"])
    OPENAI_API_BASE = _config.get('openai', {}).get('api_base', 'https://veloera.wei.bi')
    OPENAI_TEMPERATURE = float(_config.get('response', {}).get('temperature', 0.7))
    OPENAI_MAX_TOKENS = int(_config.get('response', {}).get('max_tokens', 500))
    
    # 日志配置
    LOG_LEVEL = _config.get('logging', {}).get('level', "INFO")
    
    # 安全配置（可选）
    ACCESS_TOKEN = _config.get('security', {}).get('access_token')
    
    # 响应配置
    MAX_TOKENS = int(_config.get('response', {}).get('max_tokens', 500))
    TEMPERATURE = float(_config.get('response', {}).get('temperature', 0.7))
    
    # 缓存配置
    ENABLE_CACHE = _config.get('cache', {}).get('enable', True)
    CACHE_EXPIRATION = int(_config.get('cache', {}).get('expiration', 2592000))  # 默认缓存30天
    
    # 记录配置
    ENABLE_RECORD = _config.get('record', {}).get('enable', True)  # 是否记录问答到数据库
    
    # 数据库配置 - MySQL 8.4.0
    DB_TYPE = _config.get('database', {}).get('type', "mysql")
    DB_HOST = _config.get('database', {}).get('host', "localhost")
    DB_PORT = int(_config.get('database', {}).get('port', 3306))
    DB_USER = _config.get('database', {}).get('user', "root")
    DB_PASSWORD = _config.get('database', {}).get('password', "123456")
    DB_NAME = _config.get('database', {}).get('name', "ocs_qa")
    
    # 数据库连接字符串
    SQLALCHEMY_DATABASE_URI = f"{DB_TYPE}+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    
    # Redis配置
    REDIS_ENABLED = _config.get('redis', {}).get('enabled', False)
    REDIS_HOST = _config.get('redis', {}).get('host', "localhost")
    REDIS_PORT = int(_config.get('redis', {}).get('port', 6379))
    REDIS_PASSWORD = _config.get('redis', {}).get('password', "")
    REDIS_DB = int(_config.get('redis', {}).get('db', 0))

def update_config(new_config):
    """更新系统配置"""
    from config import Config
    import json
    # 更新运行时配置
    Config.ENABLE_CACHE = new_config.get('ENABLE_CACHE', Config.ENABLE_CACHE)
    Config.CACHE_EXPIRATION = new_config.get('CACHE_EXPIRATION', Config.CACHE_EXPIRATION)
    Config.ENABLE_RECORD = new_config.get('ENABLE_RECORD', Config.ENABLE_RECORD)
    Config.OPENAI_API_KEY = new_config.get('OPENAI_API_KEY', Config.OPENAI_API_KEY)
    Config.OPENAI_MODEL = new_config.get('OPENAI_MODEL', Config.OPENAI_MODEL)
    Config.OPENAI_MODELS = new_config.get('OPENAI_MODELS', Config.OPENAI_MODELS)
    Config.OPENAI_API_BASE = new_config.get('OPENAI_API_BASE', Config.OPENAI_API_BASE)
    Config.OPENAI_TEMPERATURE = new_config.get('OPENAI_TEMPERATURE', Config.OPENAI_TEMPERATURE)
    Config.OPENAI_MAX_TOKENS = new_config.get('OPENAI_MAX_TOKENS', Config.OPENAI_MAX_TOKENS)
    Config.ACCESS_TOKEN = new_config.get('ACCESS_TOKEN', Config.ACCESS_TOKEN)
    config_data = {
        'service': {
            'host': Config.HOST,
            'port': Config.PORT,
            'debug': Config.DEBUG
        },
        'openai': {
            'api_key': Config.OPENAI_API_KEY,
            'model': Config.OPENAI_MODEL,
            'models': Config.OPENAI_MODELS,
            'api_base': Config.OPENAI_API_BASE
        },
        'cache': {
            'enable': Config.ENABLE_CACHE,
            'expiration': Config.CACHE_EXPIRATION
        },
        'security': {
            'access_token': Config.ACCESS_TOKEN,
            'secret_key': Config.SECRET_KEY if hasattr(Config, 'SECRET_KEY') else os.urandom(24).hex()
        },
        'database': {
            'type': Config.DB_TYPE,
            'host': Config.DB_HOST,
            'port': Config.DB_PORT,
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD,
            'name': Config.DB_NAME
        },
        'redis': {
            'enabled': Config.REDIS_ENABLED,
            'host': Config.REDIS_HOST,
            'port': Config.REDIS_PORT,
            'password': Config.REDIS_PASSWORD,
            'db': Config.REDIS_DB
        },
        'record': {
            'enable': Config.ENABLE_RECORD
        }
    }
    try:
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        raise e