"""凭证加密服务"""
from cryptography.fernet import Fernet
from base64 import urlsafe_b64encode
from hashlib import sha256
from app.config import settings


def get_fernet() -> Fernet:
    """获取 Fernet 加密器（基于 SECRET_KEY 派生）"""
    # 从 SECRET_KEY 派生一个 32 字节的密钥
    key = sha256(settings.secret_key.encode()).digest()
    fernet_key = urlsafe_b64encode(key)
    return Fernet(fernet_key)


def encrypt_credential(plaintext: str) -> str:
    """加密凭证"""
    if not plaintext:
        return plaintext
    fernet = get_fernet()
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    """解密凭证"""
    if not ciphertext:
        return ciphertext
    try:
        fernet = get_fernet()
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception:
        # 如果解密失败，可能是未加密的旧数据
        return ciphertext
