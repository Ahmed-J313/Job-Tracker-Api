import os

from cryptography.fernet import Fernet, InvalidToken


class TokenEncryptionNotConfigured(Exception):
    pass


def _fernet():
    key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if not key:
        raise TokenEncryptionNotConfigured("TOKEN_ENCRYPTION_KEY environment variable is required")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(raw_token):
    return _fernet().encrypt(raw_token.encode()).decode()


def decrypt_token(encrypted_token):
    try:
        return _fernet().decrypt(encrypted_token.encode()).decode()
    except InvalidToken:
        return None
