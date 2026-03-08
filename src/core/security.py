import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import settings

# 创建密码上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ========== JWT Token ==========
def create_access_token(
    subject: str | int, expires_delta: timedelta | None = None
) -> str:
    """
    生成 Access Token

    Args:
        subject: 用户标识（通常是 user_id）
        expires_delta: 过期时间增量，默认使用配置值

    Returns:
        JWT Token 字符串
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    payload = {
        "sub": str(subject),  # 用户 ID
        "exp": expire,  # 过期时间
        "iat": datetime.now(timezone.utc),  # 签发时间
        "type": "access",  # Token 类型
    }

    encoded_jwt = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    subject: str | int, expires_delta: timedelta | None = None
) -> str:
    """
    生成 Refresh Token

    Args:
        subject: 用户标识（通常是 user_id）
        expires_delta: 过期时间增量，默认使用配置值

    Returns:
        JWT Token 字符串
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )

    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",  # 标识为 Refresh Token
    }

    encoded_jwt = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> dict[str, Any]:
    """
    验证 Token 并返回 Payload

    Args:
        token: JWT Token 字符串
        token_type: Token 类型（access 或 refresh）

    Returns:
        Token 的 Payload 数据

    Raises:
        HTTPException: Token 无效或过期
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )

        # 验证 Token 类型
        if payload.get("type") != token_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"无效的 Token 类型，期望 {token_type}",
            )

        return payload

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_token(token: str) -> dict[str, Any] | None:
    """
    解析 Token（不验证签名和过期时间）

    用于调试或获取 Token 信息

    Args:
        token: JWT Token 字符串

    Returns:
        Token 的 Payload，解析失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},  # 不验证过期时间
        )
        return payload
    except JWTError:
        return None


def get_token_user_id(token: str) -> int | None:
    """
    从 Token 中提取用户 ID

    Args:
        token: JWT Token 字符串

    Returns:
        用户 ID，提取失败返回 None
    """
    payload = decode_token(token)
    if payload:
        user_id = payload.get("sub")
        return int(user_id) if user_id else None
    return None


def refresh_access_token(refresh_token: str) -> str:
    """
    使用 Refresh Token 刷新 Access Token

    Args:
        refresh_token: Refresh Token 字符串

    Returns:
        新的 Access Token

    Raises:
        HTTPException: Refresh Token 无效或过期
    """
    # 验证 Refresh Token
    payload = verify_token(refresh_token, token_type="refresh")

    # 提取用户 ID
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Token",
        )

    # 生成新的 Access Token
    new_access_token = create_access_token(subject=user_id)
    return new_access_token


# ========== 密码 ==========


def get_password_hash(password: str) -> str:
    """
    对密码进行哈希

    Args:
        password: 明文密码

    Returns:
        哈希后的密码
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码是否正确

    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码

    Returns:
        密码是否匹配
    """
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    验证密码强度

    规则：
    - 至少 8 个字符
    - 包含大写字母
    - 包含小写字母
    - 包含数字
    - 包含特殊字符

    Args:
        password: 待验证的密码

    Returns:
        (是否有效, 错误信息)
    """
    if len(password) < 8:
        return False, "密码长度至少为 8 个字符"

    if not re.search(r"[A-Z]", password):
        return False, "密码必须包含至少一个大写字母"

    if not re.search(r"[a-z]", password):
        return False, "密码必须包含至少一个小写字母"

    if not re.search(r"\d", password):
        return False, "密码必须包含至少一个数字"

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "密码必须包含至少一个特殊字符"

    return True, "密码强度符合要求"
