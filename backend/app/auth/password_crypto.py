import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

IV_LENGTH = 12


class PasswordDecryptError(Exception):
    pass


def _encryption_key() -> bytes:
    raw = settings.password_encrypt_key.strip()
    if not raw:
        raise PasswordDecryptError("未配置密码加密密钥")
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise PasswordDecryptError("密码加密密钥格式无效") from exc
    if len(key) not in {16, 24, 32}:
        raise PasswordDecryptError("密码加密密钥长度无效")
    return key


def decrypt_password(encrypted_b64: str) -> str:
    try:
        payload = base64.b64decode(encrypted_b64, validate=True)
        if len(payload) <= IV_LENGTH:
            raise PasswordDecryptError("密文格式无效")
        iv = payload[:IV_LENGTH]
        ciphertext = payload[IV_LENGTH:]
        plaintext = AESGCM(_encryption_key()).decrypt(iv, ciphertext, None)
        return plaintext.decode("utf-8")
    except PasswordDecryptError:
        raise
    except Exception as exc:
        raise PasswordDecryptError("密码解密失败") from exc
