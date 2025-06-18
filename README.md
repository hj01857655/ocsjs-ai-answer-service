# EduBrain AI - 智能题库系统

> **重大更新通知**: 本项目已升级为第三方API代理池架构，支持多个第三方API服务的负载均衡和故障转移。配置结构已从单一API配置升级为代理池数组配置，提供更高的可靠性和灵活性。

这是一个基于Python和多第三方AI API的新一代智能题库服务，专为[OCS (Online Course Script)](https://github.com/ocsjs/ocsjs)设计，可以通过AI自动回答题目。此服务实现了与OCS AnswererWrapper兼容的API接口，方便用户将AI能力整合到OCS题库搜索中。

## ⚠️ 重要提示

> [!IMPORTANT]
> - 本项目仅供个人学习使用，不保证稳定性，且不提供任何技术支持。
> - 使用者必须在遵循各第三方AI服务提供商的使用条款以及**法律法规**的情况下使用，不得用于非法用途。
> - 根据[《生成式人工智能服务管理暂行办法》](http://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm)的要求，请勿对中国地区公众提供一切未经备案的生成式人工智能服务。
> - 使用者应当遵守相关法律法规，承担相应的法律责任
> - 服务不对AI生成内容的准确性做出保证

## 🌟 功能特点

- 🌐 **第三方API代理池**：支持多个第三方API服务的负载均衡和故障转移
- 💡 **多AI供应商支持**：支持OpenAI、Anthropic、Google等多个AI供应商
- 🔄 **OCS兼容**：完全兼容OCS的AnswererWrapper题库接口
- 🚀 **高性能缓存**：Redis + 内存双重缓存，快速响应请求
- 🔒 **安全可靠**：支持访问令牌验证，完整的用户权限管理
- 💬 **多种题型**：支持单选、多选、判断、填空等题型
- 📊 **数据统计**：实时监控服务状态和使用情况
- 🌐 **Web管理界面**：现代化的响应式管理仪表盘
- 📱 **移动友好**：完美适配手机和平板设备
- 👥 **用户管理**：完整的用户注册、登录、权限管理系统
- 🔑 **代理池监控**：智能代理选择、密钥轮换和实时监控
- 🖼️ **图片代理**：解决超星平台图片403问题
- 📚 **题库管理**：完整的题库增删改查和导出功能
- ⚡ **智能故障转移**：自动检测代理状态，无缝切换到可用代理
- 🎯 **负载均衡**：支持多种代理选择策略，优化性能和可靠性

## 📋 系统要求

- Python 3.8+ (推荐 Python 3.9+)
- MySQL 8.0+ (用于数据存储)
- Redis (可选，用于缓存)
- 第三方AI API密钥（支持OpenAI兼容接口的服务）

## 🚀 快速开始

### 1. 克隆代码库

```bash
git clone https://github.com/LynnGuo666/ocsjs-ai-answer-service.git
cd ocsjs-ai-answer-service
```

### 2. 创建虚拟环境（推荐）

```bash
# 创建虚拟环境
python -m venv .venv

# Windows 激活虚拟环境
.venv\Scripts\activate

# Linux/Mac 激活虚拟环境
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 数据库配置

确保MySQL服务运行，并创建数据库：

```sql
CREATE DATABASE ocs_qa CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. 配置config.json

将`config.json.example`复制为`config.json`并填写必要的配置信息：

```bash
# Windows
copy config.json.example config.json

# Linux/Mac
cp config.json.example config.json
```

编辑`config.json`文件，配置数据库和第三方API代理池：

```json
{
  "service": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false
  },
  "database": {
    "type": "mysql",
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "your_db_password",
    "name": "ocs_qa"
  },
  "third_party_apis": [
    {
      "name": "主要API服务",
      "api_base": "https://api.example.com",
      "api_keys": [
        "sk-your-api-key-1",
        "sk-your-api-key-2"
      ],
      "model": "claude-3-5-sonnet",
      "models": [
        "claude-3-5-sonnet",
        "gpt-4o-mini",
        "gemini-1.5-pro"
      ],
      "is_active": true,
      "priority": 1
    }
  ],
  "cache": {
    "enable": true,
    "expiration": 2592000
  },
  "security": {
    "access_token": "your_access_token_here"
  }
}
```

### 6. 启动服务

```bash
python app.py
```

服务将默认运行在`http://localhost:5000`

### 7. 访问Web界面

打开浏览器访问 `http://localhost:5000` 进入管理界面。首次使用需要注册管理员账户。

### 8. 在OCS中配置使用

在OCS的自定义题库配置中添加如下配置：

```json
[
  {
    "name": "AI智能题库",
    "url": "http://localhost:5000/api/search",
    "method": "get",
    "contentType": "json",
    "headers": {
      "X-Access-Token": "your_access_token_here"
    },
    "data": {
      "title": "${title}",
      "type": "${type}",
      "options": "${options}"
    },
    "handler": "return (res)=> res.code === 1 ? [res.question, res.answer] : [res.msg, undefined]"
  }
]
```

> **注意**: 如果配置了访问令牌，需要在headers中添加`X-Access-Token`字段。

## 📚 Web管理界面

### 主要功能页面

- **仪表盘** (`/dashboard`): 系统状态监控和问答记录统计
- **AI实时搜题** (`/ai-search`): 在线测试AI答题功能
- **题库管理** (`/questions`): 题库增删改查和数据导出
- **系统日志** (`/logs`): 查看和管理系统日志
- **代理池监控** (`/proxy-monitor`): 第三方API代理池实时监控和管理
- **系统设置** (`/settings`): 代理池配置和系统参数管理

### 用户权限

- **普通用户**: 可以查看仪表盘和使用AI搜题功能
- **管理员**: 拥有所有功能权限，包括用户管理、系统配置等

## 🔌 API接口说明

### 核心搜索接口

**URL**: `/api/search`

**方法**: `GET` 或 `POST`

**请求头**:
```
X-Access-Token: your_access_token_here (可选)
```

**参数**:

| 参数名   | 类型   | 必填 | 说明                                                     |
|---------|--------|------|----------------------------------------------------------|
| title   | string | 是   | 题目内容                                                 |
| type    | string | 否   | 题目类型 (single-单选, multiple-多选, judgement-判断, completion-填空) |
| options | string | 否   | 选项内容，通常是A、B、C、D选项的文本                       |
| proxy   | string | 否   | 指定代理服务名称                                         |
| model   | string | 否   | 指定模型名称                                             |

**成功响应**:

```json
{
  "code": 1,
  "question": "问题内容",
  "answer": "AI生成的答案",
  "proxy": "主要API服务",
  "model": "gpt-4o-mini",
  "cached": false,
  "response_time": 1.23
}
```

**失败响应**:

```json
{
  "code": 0,
  "msg": "错误信息"
}
```

### 系统监控接口

#### 健康检查

**URL**: `/api/health`

**方法**: `GET`

**响应**:

```json
{
  "status": "ok",
  "message": "AI题库服务运行正常",
  "version": "1.1.0",
  "cache_enabled": true,
  "model": "gpt-4o-mini"
}
```

#### 缓存管理

**URL**: `/api/cache/clear`

**方法**: `POST`

**响应**:

```json
{
  "success": true,
  "message": "缓存已清除",
  "cleared_count": 150
}
```

### 题库管理接口

#### 获取题库列表

**URL**: `/api/questions`

**方法**: `GET`

**参数**:
- `page`: 页码 (默认: 1)
- `per_page`: 每页数量 (默认: 20)
- `search`: 搜索关键词
- `type`: 题目类型筛选

#### 导出题库

**URL**: `/api/questions/export`

**方法**: `GET`

**参数**:
- `format`: 导出格式 (csv, json)
- `type`: 题目类型筛选

### 图片代理接口

**URL**: `/api/image/proxy`

**方法**: `GET`

**参数**:
- `url`: 图片URL (需要URL编码)

**说明**: 用于解决超星平台图片403问题

## 🌐 第三方API代理池

### 代理池架构

本系统采用先进的代理池架构，支持多个第三方API服务的统一管理：

- **负载均衡**: 自动在多个代理间分配请求
- **故障转移**: 自动检测代理状态，无缝切换到可用代理
- **优先级管理**: 支持代理优先级设置，优先使用高优先级代理
- **密钥轮换**: 每个代理支持多个API密钥的智能轮换
- **实时监控**: 代理池状态实时监控和统计

### 代理池配置

在 `config.json` 中配置代理池：

```json
{
  "third_party_apis": [
    {
      "name": "主要API服务",
      "api_base": "https://api.example.com",
      "api_keys": [
        "sk-key1",
        "sk-key2",
        "sk-key3"
      ],
      "model": "gpt-4o-mini",
      "models": [
        "gpt-4o-mini",
        "gpt-4o",
        "claude-3-sonnet"
      ],
      "is_active": true,
      "priority": 1
    },
    {
      "name": "备用API服务",
      "api_base": "https://backup-api.example.com",
      "api_keys": [
        "sk-backup-key1",
        "sk-backup-key2"
      ],
      "model": "gpt-4o",
      "models": [
        "gpt-4o",
        "gpt-4o-mini"
      ],
      "is_active": true,
      "priority": 2
    }
  ]
}
```

### 配置字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 代理服务名称，用于标识和显示 |
| `api_base` | string | 是 | API基础URL地址 |
| `api_keys` | array | 是 | API密钥数组，支持多个密钥轮换 |
| `model` | string | 是 | 默认使用的模型名称 |
| `models` | array | 是 | 支持的模型列表 |
| `is_active` | boolean | 是 | 是否激活此代理（true/false） |
| `priority` | number | 是 | 优先级（数字越小优先级越高） |

### 代理选择策略

系统支持多种代理选择策略：

1. **优先级策略**: 优先使用priority值最小的激活代理
2. **随机策略**: 从激活代理中随机选择（负载均衡）
3. **模型匹配**: 根据请求的模型自动选择支持该模型的代理
4. **故障转移**: 当前代理失败时自动切换到下一个可用代理

### 代理池监控

访问 `/proxy-monitor` 页面可以实时监控代理池状态：

- **代理池汇总**: 总代理数、激活代理数、总密钥数、支持模型数
- **代理详情**: 每个代理的状态、优先级、密钥数量、模型支持
- **实时刷新**: 支持自动刷新和手动刷新
- **密钥管理**: 查看每个代理的密钥列表和当前使用的密钥

## 🚀 部署建议

### 生产环境部署

#### 使用Gunicorn部署

对于生产环境，建议使用Gunicorn作为WSGI服务器：

```bash
# 基本部署
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# 推荐的生产配置
gunicorn -w 4 -b 0.0.0.0:5000 \
  --timeout 120 \
  --keep-alive 2 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  app:app
```

#### 使用Docker部署

创建 `Dockerfile`:

```Dockerfile
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建日志目录
RUN mkdir -p logs

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "--timeout", "120", "app:app"]
```

构建并运行Docker容器：

```bash
# 构建镜像
docker build -t edubrain-ai .

# 运行容器
docker run -d \
  --name edubrain-ai \
  -p 5000:5000 \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/logs:/app/logs \
  edubrain-ai
```

#### 使用Docker Compose

创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./config.json:/app/config.json
      - ./logs:/app/logs
    depends_on:
      - mysql
      - redis
    environment:
      - FLASK_ENV=production

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: your_password
      MYSQL_DATABASE: ocs_qa
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "3306:3306"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  mysql_data:
  redis_data:
```

启动服务：

```bash
docker-compose up -d
```

## ❓ 常见问题

### 1. 数据库连接问题

**问题**: 启动时出现数据库连接错误

**解决方法**:
- 确保MySQL服务正在运行
- 检查config.json中的数据库配置
- 确认数据库用户权限
- 创建数据库：`CREATE DATABASE ocs_qa CHARACTER SET utf8mb4;`

### 2. 第三方API连接错误

**问题**: 遇到 `APIConnectionError` 或 `API调用失败`

**可能原因**:
- API密钥无效或过期
- API基础URL配置错误
- 网络连接问题
- API配额不足
- 代理服务不可用

**解决方法**:
- 检查config.json中的third_party_apis配置
- 确认API密钥有效性
- 测试网络连接
- 检查API使用配额
- 访问 `/proxy-monitor` 查看代理池状态
- 检查代理的 `is_active` 状态

### 3. 虚拟环境问题

**问题**: 依赖安装失败或模块导入错误

**解决方法**:
```bash
# 重新创建虚拟环境
rm -rf .venv  # Linux/Mac
rmdir /s .venv  # Windows

python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 权限和认证问题

**问题**: 无法访问管理功能

**解决方法**:
- 确保已注册管理员账户
- 检查用户权限设置
- 清除浏览器缓存和Cookie
- 检查访问令牌配置

### 5. AI答案准确性

**注意事项**:
- AI答案仅供参考，不保证100%准确
- 建议与原题选项对照验证
- 复杂题目可能需要人工判断
- 多选题格式已自动处理为`A#B#C`格式

### 6. 性能优化

**缓存配置**:
- 启用Redis缓存提升性能
- 调整缓存过期时间
- 定期清理过期缓存

**数据库优化**:
- 定期清理历史记录
- 添加适当的数据库索引
- 监控数据库性能

### 7. 代理池配置问题

**问题**: 代理池无法正常工作或显示异常

**可能原因**:
- 配置格式错误
- 代理服务不可用
- 密钥配置错误

**解决方法**:
- 检查 `config.json` 中 `third_party_apis` 数组格式
- 确保每个代理都有必填字段：`name`, `api_base`, `api_keys`, `model`, `models`, `is_active`, `priority`
- 访问 `/proxy-monitor` 查看代理池实时状态
- 检查代理服务的网络连接
- 验证API密钥的有效性

**配置检查清单**:
```json
{
  "third_party_apis": [
    {
      "name": "必填：代理名称",
      "api_base": "必填：API基础URL",
      "api_keys": ["必填：至少一个API密钥"],
      "model": "必填：默认模型",
      "models": ["必填：支持的模型列表"],
      "is_active": true,
      "priority": 1
    }
  ]
}
```

### 8. 图片显示问题

**问题**: 超星平台图片无法显示

**解决方法**:
- 图片代理服务已自动处理
- 确保 `/api/image/proxy` 接口正常
- 检查网络连接和防火墙设置

## 📁 项目结构

```
ocsjs-ai-answer-service/
├── config/                    # 配置目录
│   ├── __init__.py
│   ├── config.py             # 主配置文件
│   ├── api_proxy_pool.py     # 第三方API代理池管理
│   └── api_pool.py           # 向后兼容的API池管理
├── models/                   # 数据模型
│   ├── __init__.py
│   └── models.py            # 数据库模型定义
├── routes/                   # 路由模块
│   ├── __init__.py
│   ├── auth.py              # 用户认证路由
│   ├── questions.py         # 题库管理路由
│   ├── logs.py              # 日志管理路由
│   ├── proxy_pool.py        # 代理池监控路由
│   ├── settings.py          # 设置管理路由
│   └── image_proxy.py       # 图片代理路由
├── services/                # 服务层
│   ├── __init__.py
│   ├── model_service.py     # AI模型服务
│   ├── cache.py             # 缓存服务
│   └── key_switcher.py      # 密钥管理服务
├── utils/                   # 工具函数
│   ├── __init__.py
│   ├── utils.py             # 通用工具函数
│   ├── auth.py              # 认证工具
│   ├── logger.py            # 日志工具
│   ├── question_cleaner.py  # 题目清理工具
│   ├── get_models_list.py   # 模型列表获取工具
│   └── clean_question_prefixes.py  # 题目前缀清理工具
├── static/                  # 静态资源
│   ├── css/                 # 样式文件
│   ├── js/                  # JavaScript文件
│   └── img/                 # 图片资源
├── templates/               # 模板文件
│   ├── base.html            # 基础模板
│   ├── dashboard.html       # 仪表盘
│   ├── login.html           # 登录页面
│   ├── questions.html       # 题库管理
│   ├── logs.html            # 日志查看
│   ├── proxy_pool.html      # 代理池监控
│   ├── settings.html        # 系统设置
│   └── ...                  # 其他模板
├── logs/                    # 日志目录
├── backups/                 # 备份目录
├── .venv/                   # 虚拟环境（推荐）
├── app.py                   # 主应用文件
├── config.json              # 配置文件
├── config.json.example      # 配置示例
├── config_example_multi_proxy.json  # 多代理配置示例
├── requirements.txt         # 依赖列表
├── .gitignore              # Git忽略文件
└── README.md               # 项目说明
```

## 🔧 配置说明

### 完整配置示例

```json
{
  "service": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false
  },
  "database": {
    "type": "mysql",
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "your_password",
    "name": "ocs_qa"
  },
  "redis": {
    "enabled": true,
    "host": "localhost",
    "port": 6379,
    "password": "",
    "db": 0
  },
  "third_party_apis": [
    {
      "name": "主要API服务",
      "api_base": "https://api.example.com",
      "api_keys": [
        "sk-key1",
        "sk-key2",
        "sk-key3"
      ],
      "model": "gpt-4o-mini",
      "models": [
        "gpt-4o-mini",
        "gpt-4o",
        "claude-3-sonnet"
      ],
      "is_active": true,
      "priority": 1
    },
    {
      "name": "备用API服务",
      "api_base": "https://backup-api.example.com",
      "api_keys": [
        "sk-backup-key1"
      ],
      "model": "gpt-4o",
      "models": [
        "gpt-4o",
        "gpt-4o-mini"
      ],
      "is_active": true,
      "priority": 2
    }
  ],
  "cache": {
    "enable": true,
    "expiration": 2592000
  },
  "security": {
    "access_token": "your_secure_token",
    "secret_key": "your_secret_key"
  },
  "logging": {
    "level": "INFO"
  },
  "record": {
    "enable": true
  },
  "response": {
    "max_tokens": 500,
    "temperature": 0.7
  },
  "default_provider": "third_party_api_pool"
}
```

## 🔧 代理池管理

### 代理池健康检查

系统提供了代理池的健康检查和监控功能：

- **实时监控**: 访问 `/proxy-monitor` 查看代理池实时状态
- **自动故障转移**: 系统自动检测代理状态，失败时切换到备用代理
- **负载均衡**: 支持多种代理选择策略，优化性能

### 代理池API接口

```bash
# 获取代理池状态
curl http://localhost:5000/api/key_pool

# 清除所有缓存
curl -X POST http://localhost:5000/api/cache/clear_all
```

### 代理池配置验证

可以通过以下方式验证代理池配置：

1. **Web界面**: 访问 `/proxy-monitor` 查看配置状态
2. **API接口**: 调用 `/api/key_pool` 获取详细信息
3. **日志检查**: 查看 `/logs` 页面的系统日志

## 🤝 贡献指南

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目仅供学习和研究使用，请遵守相关法律法规。

## 🙏 致谢

- [OCS (Online Course Script)](https://github.com/ocsjs/ocsjs) - 提供题库接口标准
- [OpenAI](https://openai.com/) - 提供强大的AI模型
- [Flask](https://flask.palletsprojects.com/) - 优秀的Python Web框架

---

**⚠️ 免责声明**: 本项目仅供学习交流使用，使用者需自行承担使用风险，开发者不对任何后果负责。