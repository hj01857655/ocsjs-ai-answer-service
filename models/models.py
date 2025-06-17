# -*- coding: utf-8 -*-
"""
数据库模型定义
"""
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import hashlib
import uuid

from config import Config

# 创建SQLAlchemy基类
Base = declarative_base()

# 问答记录模型
class QARecord(Base):
    __tablename__ = 'qa_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False, comment='问题内容')
    type = Column(String(20), nullable=True, comment='问题类型')
    options = Column(Text, nullable=True, comment='选项内容')
    answer = Column(Text, nullable=True, comment='回答内容')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'question': self.question,
            'type': self.type,
            'options': self.options,
            'answer': self.answer,
            'time': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp': self.created_at.isoformat()
        }

# 用户模型
class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, comment='用户名')
    password_hash = Column(String(128), nullable=False, comment='密码哈希值')
    salt = Column(String(32), nullable=False, comment='密码盐')
    email = Column(String(100), unique=True, nullable=True, comment='邮箱')
    role = Column(String(20), default='user', comment='用户角色')
    is_admin = Column(Boolean, default=False, comment='是否管理员')
    is_active = Column(Boolean, default=True, comment='是否激活')
    last_login = Column(DateTime, nullable=True, comment='最后登录时间')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    
    def set_password(self, password):
        """设置密码"""
        # 生成盐
        self.salt = uuid.uuid4().hex
        # 生成密码哈希
        self.password_hash = self._hash_password(password, self.salt)
    
    def verify_password(self, password):
        """验证密码"""
        return self.password_hash == self._hash_password(password, self.salt)
    
    def _hash_password(self, password, salt):
        """哈希密码"""
        # 使用sha256算法和盐值哈希密码
        hash_obj = hashlib.sha256((password + salt).encode('utf-8'))
        return hash_obj.hexdigest()
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'last_login': self.last_login.strftime('%Y-%m-%d %H:%M:%S') if self.last_login else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }

# 模型供应商模型
class ModelProvider(Base):
    __tablename__ = 'model_providers'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, comment='供应商名称')
    api_key = Column(String(128), nullable=True, comment='API密钥')
    api_base = Column(String(256), nullable=True, comment='API基础URL')
    models = Column(Text, nullable=True, comment='可用模型列表')
    default_model = Column(String(64), nullable=True, comment='默认模型')
    is_active = Column(Boolean, default=True, comment='是否激活')
    temperature = Column(String(16), nullable=True, comment='Temperature参数')
    max_tokens = Column(Integer, nullable=True, comment='Max Tokens参数')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'api_key': self.api_key,
            'api_base': self.api_base,
            'models': self.models,
            'default_model': self.default_model,
            'is_active': self.is_active,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
        }

# 用户会话模型
class UserSession(Base):
    __tablename__ = 'user_sessions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, comment='用户ID')
    session_id = Column(String(64), unique=True, nullable=False, comment='会话ID')
    ip_address = Column(String(50), nullable=True, comment='IP地址')
    user_agent = Column(String(255), nullable=True, comment='用户代理')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    expires_at = Column(DateTime, nullable=False, comment='过期时间')
    
    @classmethod
    def create_session(cls, db, user_id, ip_address=None, user_agent=None, expires_days=30):
        """创建新会话"""
        # 生成唯一会话ID
        session_id = uuid.uuid4().hex
        # 计算过期时间
        expires_at = datetime.now() + timedelta(days=expires_days)
        
        # 创建会话记录
        session = cls(
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )
        
        # 保存到数据库
        db.add(session)
        db.commit()
        
        return session_id
    
    @classmethod
    def validate_session(cls, db, session_id):
        """验证会话是否有效"""
        if not session_id:
            return None
        
        # 查询会话
        session = db.query(cls).filter(
            cls.session_id == session_id,
            cls.expires_at > datetime.now()
        ).first()
        
        if not session:
            return None
        
        return session.user_id
    
    @classmethod
    def delete_session(cls, db, session_id):
        """删除会话"""
        session = db.query(cls).filter(cls.session_id == session_id).first()
        if session:
            db.delete(session)
            db.commit()
            return True
        return False

# 用户认证函数
def authenticate_user(db, username, password):
    """认证用户"""
    # 查询用户
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    
    # 验证密码
    if user and user.verify_password(password):
        return user
    
    return None

def get_user_by_id(db, user_id):
    """根据ID获取用户"""
    return db.query(User).filter(User.id == user_id).first()

def create_user(db, username, password, email=None, role='user', is_admin=False):
    """创建新用户"""
    # 检查用户名是否已存在
    if db.query(User).filter(User.username == username).first():
        return None, "用户名已被占用"
    
    # 检查邮箱是否已存在
    if email and db.query(User).filter(User.email == email).first():
        return None, "邮箱已被注册"
    
    # 创建用户
    user = User(
        username=username,
        email=email,
        role=role,
        is_admin=is_admin
    )
    
    # 设置密码
    user.set_password(password)
    
    # 保存到数据库
    db.add(user)
    db.commit()
    
    return user, None

# 数据库连接
def init_db():
    """初始化数据库连接"""
    try:
        engine = create_engine(Config.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True, pool_recycle=3600)
        # 创建表
        Base.metadata.create_all(engine)
        # 创建会话工厂
        return sessionmaker(bind=engine)
    except Exception as e:
        import logging
        logging.getLogger('ai_answer_service').error(f"初始化数据库时出错: {str(e)}")
        raise

# 会话工厂
Session = None

def get_db_session():
    """获取数据库会话
    
    注意：每次调用都会返回一个新的会话实例。使用后需要手动关闭或在请求结束时自动关闭。
    """
    global Session
    try:
        if Session is None:
            Session = init_db()
        return Session()
    except Exception as e:
        import logging
        logging.getLogger('ai_answer_service').error(f"创建数据库会话时出错: {str(e)}")
        return None

def close_db_session(session):
    """关闭数据库会话
    
    如果会话有未提交的事务，会先回滚再关闭。
    """
    if session:
        try:
            # 安全地回滚任何未提交的事务
            try:
                session.rollback()
                import logging
                logging.getLogger('ai_answer_service').debug("关闭数据库会话前回滚事务")
            except Exception as rollback_error:
                import logging
                logging.getLogger('ai_answer_service').warning(f"回滚事务时出错: {str(rollback_error)}")
                
            # 关闭会话
            session.close()
        except Exception as e:
            import logging
            logging.getLogger('ai_answer_service').error(f"关闭数据库会话时出错: {str(e)}")
            # 尝试强制关闭
            try:
                session.close()
            except:
                pass