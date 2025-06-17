import requests
from flask import Blueprint, request, Response, current_app
import re
from urllib.parse import urlparse
import logging

# 创建蓝图
image_proxy_bp = Blueprint('image_proxy', __name__)

# 允许的域名列表
ALLOWED_DOMAINS = [
    'p.ananas.chaoxing.com',
    'chaoxing.com',
    'image.chaoxing.com'
]

# 超星平台请求头
CHAOXING_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "sec-ch-ua": "\"Chromium\";v=\"136\", \"Microsoft Edge\";v=\"136\", \"Not.A/Brand\";v=\"99\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1"
}

# 超星平台Cookie
CHAOXING_COOKIES = {
    "fid": "2207", 
    "source": "\"\"", 
    "uname": "bk_g0oP", 
    "_uid": "328843295", 
    "_d": "1748545406405", 
    "UID": "328843295",
    "vc3": "R7R2Wy%2B22Xcp%2BkfXYTST2rtAx6GwgYSLR8qMOTBp7JNFcJ6c%2B7Tm2UgtGv2CvY1p6%2FAInu8fTKodOCO8tF7sRq2IeijAZjomOKvDQM1hQmJGFQ5m9ljZ%2Bail76Yj%2F7z92SEm9Tp9ShHFLWfcBtzPscUkpH099WYx5aU%2BFrHd0Zs%3De21059e5bb70f54807f23090ff67935c", 
    "uf": "da0883eb5260151e960de52a4fc1b6a941c9fb6d5a29f2f9686a29e5e0eff6a7a698eb83c701a3b87181feeace21da30913b662843f1f4ad7631dba781cdd959f44425e20f927c6b0b3b56d2dabeca85b919cf4f30ba0bf0c589688fe9065f49fd68be96b6183b1a134bf0ea08b167a524fa3b4716ba5cfa2422ec74aea640d9f3d718d572fcfc7c", 
    "cx_p_token": "eca970d5faddd22f51e1d60b985867d7", 
    "p_auth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOiIzMjg4NDMyOTUiLCJsb2dpblRpbWUiOjE3NDg1NDU0MDY0MDcsImV4cCI6MTc0OTE1MDIwNn0.YfNQIhEgK0NAu2Tb8CHXlS_uuy_QQYi2mQ8M3ZZE3d8", 
    "xxtenc": "06d9d9ae15a84e71dcb8dd4cb44b9035", 
    "DSSTASH_LOG": "C_38-UN_751-US_328843295-T_1748545406407", 
    "spaceFid": "2207", 
    "spaceRoleId": "1", 
    "tl": "1", 
    "jrose": "FCDA479AF7694F936718A24B59D4BED6.fms-2697320765-x47v4"
}

@image_proxy_bp.route('/proxy', methods=['GET'])
def proxy_image():
    """
    图片代理服务，解决超星平台图片403问题
    """
    # 获取目标URL
    url = request.args.get('url')
    
    if not url:
        return Response("Missing URL parameter", status=400)
    
    # 防止递归代理
    if '/api/image/proxy' in url:
        current_app.logger.error(f"Recursive proxy detected: {url}")
        return Response("Recursive proxy request detected", status=400)
        
    # 检查URL安全性
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    
    # 记录请求信息
    current_app.logger.info(f"Processing image proxy request for: {url} from domain: {domain}")
    
    # 检查是否是允许的域名
    if not any(domain.endswith(allowed_domain) for allowed_domain in ALLOWED_DOMAINS):
        current_app.logger.warning(f"Domain not allowed: {domain}")
        return Response(f"Domain not allowed: {domain}", status=403)
    
    try:
        # 记录请求详情
        current_app.logger.info(f"Sending request to: {url} with headers: {CHAOXING_HEADERS}")
        
        # 发送请求获取图片
        # 发送请求获取图片
        response = requests.get(
            url, 
            headers=CHAOXING_HEADERS,
            cookies=CHAOXING_COOKIES,
            stream=True,
            timeout=10
        )
        
        # 检查响应状态
        if response.status_code != 200:
            current_app.logger.error(f"Proxy error: {response.status_code} for URL {url}")
            current_app.logger.error(f"Response headers: {response.headers}")
            return Response(f"Error fetching image: {response.status_code}", status=response.status_code)
        
        # 记录成功响应
        current_app.logger.info(f"Successfully fetched image from {url}, content-type: {response.headers.get('content-type')}")
        
        # 创建响应对象
        proxy_response = Response(
            response.iter_content(chunk_size=1024),
            status=response.status_code
        )
        
        # 设置响应头
        for key, value in response.headers.items():
            if key.lower() not in ['content-encoding', 'content-length', 'transfer-encoding', 'connection']:
                proxy_response.headers[key] = value
        
        # 设置缓存控制
        proxy_response.headers['Cache-Control'] = 'public, max-age=86400'  # 缓存24小时
        proxy_response.headers['Access-Control-Allow-Origin'] = '*'  # 允许跨域
        proxy_response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'  # 设置引用策略
        
        return proxy_response
        
    except requests.exceptions.Timeout:
        current_app.logger.error(f"Timeout error for URL {url}")
        return Response("Request timed out while fetching image", status=504)
    except requests.exceptions.ConnectionError:
        current_app.logger.error(f"Connection error for URL {url}")
        return Response("Failed to connect to the image server", status=502)
    except requests.exceptions.TooManyRedirects:
        current_app.logger.error(f"Too many redirects for URL {url}")
        return Response("Too many redirects while fetching image", status=502)
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Request error for URL {url}: {str(e)}")
        return Response(f"Error fetching image: {str(e)}", status=500)
    except Exception as e:
        current_app.logger.error(f"Unexpected error for URL {url}: {str(e)}")
        return Response("An unexpected error occurred", status=500)

# 注册蓝图函数
def register_image_proxy_bp(app):
    app.register_blueprint(image_proxy_bp, url_prefix='/api/image')
