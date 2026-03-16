"""
短代码生成工具
用于生成问卷短代码（如 abc123, x7k9p2）
"""
import random
import string
from typing import Optional


# 排除易混淆字符：0, O, o, 1, I, l
AMBIGUOUS_CHARS = {'0', 'O', 'o', '1', 'I', 'l'}
SHORT_CODE_CHARS = ''.join(set(string.ascii_lowercase + string.digits) - AMBIGUOUS_CHARS)


def generate_short_code(length: int = 6) -> str:
    """
    生成随机短代码
    
    Args:
        length: 代码长度，默认6位
    
    Returns:
        随机短代码，如 "abc123"
    """
    return ''.join(random.choices(SHORT_CODE_CHARS, k=length))


def generate_unique_short_code(db, length: int = 6, max_attempts: int = 10) -> Optional[str]:
    """
    生成唯一的短代码（检查数据库是否已存在）
    
    Args:
        db: 数据库会话
        length: 代码长度
        max_attempts: 最大尝试次数
    
    Returns:
        唯一短代码，如果无法生成则返回 None
    """
    from app.models import Study
    
    for _ in range(max_attempts):
        code = generate_short_code(length)
        # 检查是否已存在
        existing = db.query(Study).filter(Study.code == code).first()
        if not existing:
            return code
    
    # 如果6位无法生成唯一代码，尝试7位
    if length < 10:
        return generate_unique_short_code(db, length + 1, max_attempts)
    
    return None


def validate_short_code(code: str) -> bool:
    """
    验证短代码格式是否有效
    
    规则：
    - 长度3-20位
    - 只能包含小写字母、数字、连字符
    - 不能以连字符开头或结尾
    
    Args:
        code: 短代码
    
    Returns:
        是否有效
    """
    if not code:
        return False
    
    if len(code) < 3 or len(code) > 20:
        return False
    
    # 允许的字符：小写字母、数字、连字符
    allowed_chars = set(SHORT_CODE_CHARS + '-')
    if not all(c in allowed_chars for c in code):
        return False
    
    # 不能以连字符开头或结尾
    if code.startswith('-') or code.endswith('-'):
        return False
    
    return True


def normalize_short_code(code: str) -> str:
    """
    规范化短代码
    - 转小写
    - 去除首尾空格
    """
    if not code:
        return ""
    return code.strip().lower()


# 预定义的短代码黑名单（保留给系统使用）
RESERVED_CODES = {
    'admin', 'api', 'www', 'app', 'test', 'demo',
    'default', 'new', 'create', 'edit', 'delete',
    'study', 'studies', 'survey', 'surveys',
    'user', 'users', 'participant', 'participants',
    'login', 'logout', 'register', 'signup',
    'help', 'support', 'contact', 'about',
    'static', 'uploads', 'exports', 'scripts',
    'null', 'none', 'undefined', 'true', 'false',
}


def is_reserved_code(code: str) -> bool:
    """检查短代码是否是保留字"""
    return code.lower() in RESERVED_CODES
