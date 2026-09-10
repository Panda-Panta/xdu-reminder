# Copyright 2026 XDU Reminder Service
# AES 加密模块 — 兼容 IDS 统一认证 / 滑块验证码 / 电费系统
#
# 移植自 traintime_pda:
#   - ids_session.dart → aes_encrypt_ids()
#   - network_client.dart → aes_encrypt_captcha()
#   - energy_session.dart → aes_encrypt_energy()

import base64
import json
import random
import string

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad


def aes_encrypt_ids(password: str, key: str) -> str:
    """IDS 登录密码加密

    对应 Dart: IDSSession.aesEncrypt(toEnc, key)
    - 在密码前拼接 "xidianscriptsxdu" × 4 作为盐值
    - AES-CBC 加密，IV = "xidianscriptsxdu"
    - 手动 PKCS7 填充

    Args:
        password: 明文密码
        key: 从登录页 pwdEncryptSalt 获取的 AES 密钥
    Returns:
        Base64 编码的加密结果
    """
    salt = "xidianscriptsxdu"
    plaintext = (salt * 4) + password
    plaintext_bytes = plaintext.encode("utf-8")

    # PKCS7 padding
    block_size = 16
    padding_length = block_size - (len(plaintext_bytes) % block_size)
    plaintext_bytes += bytes([padding_length] * padding_length)

    cipher = AES.new(
        key.encode("utf-8"),
        AES.MODE_CBC,
        iv=salt.encode("utf-8"),
    )
    encrypted = cipher.encrypt(plaintext_bytes)
    return base64.b64encode(encrypted).decode("utf-8")


# 验证码 payload 加密用的字符集
_AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"


def aes_encrypt_captcha(text: str, key_bytes: bytes) -> str:
    """滑块验证码 payload 加密

    对应 Dart: network_client.dart 中的 aesEncrypt(text, keyBytes)
    - 生成 80 个随机字符 (前 64 字节作为 nonce，第 65-80 字节作为 IV)
    - AES-CBC PKCS7 加密
    - 返回 Base64

    Args:
        text: 待加密的 JSON payload
        key_bytes: 16 字节 AES 密钥 (来自验证码图片最后 16 字节)
    Returns:
        Base64 编码的加密结果
    """
    # 生成 80 个随机字符
    rand_str = "".join(random.choice(_AES_CHARS) for _ in range(80))
    # 前 64 字节作为 nonce 前缀
    plain = rand_str[:64] + text
    # 第 65-80 字节作为 IV
    iv = rand_str[64:80].encode("utf-8")

    cipher = AES.new(key_bytes, AES.MODE_CBC, iv=iv)
    padded = pad(plain.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded)
    return base64.b64encode(encrypted).decode("utf-8")


def aes_encrypt_energy(data: dict | str, key: str = "1234567812345678",
                       iv: str = "1234567812345678") -> str:
    """电费系统 API 请求数据加密

    对应 Dart: EnergySession._request() 中的 AES 加密
    - 标准 AES-CBC，固定密钥和 IV
    - PKCS7 填充

    Args:
        data: 待加密的字典或 JSON 字符串
        key: AES 密钥 (默认 "1234567812345678")
        iv: AES IV (默认 "1234567812345678")
    Returns:
        Base64 编码的加密结果
    """
    if isinstance(data, dict):
        plaintext = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    else:
        plaintext = data

    cipher = AES.new(
        key.encode("utf-8"),
        AES.MODE_CBC,
        iv=iv.encode("utf-8"),
    )
    padded = pad(plaintext.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded)
    return base64.b64encode(encrypted).decode("utf-8")
