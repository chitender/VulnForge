import json
from cryptography.fernet import Fernet


class LocalKEKProvider:
    def __init__(self, master_key: str):
        self._fernet = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)

    def encrypt_dek(self, dek: bytes) -> bytes:
        return self._fernet.encrypt(dek)

    def decrypt_dek(self, dek_enc: bytes) -> bytes:
        return self._fernet.decrypt(dek_enc)


class CredentialStore:
    def __init__(self, kek_provider: LocalKEKProvider | None = None):
        if kek_provider is None:
            from app.core.config import settings
            kek_provider = LocalKEKProvider(settings.MASTER_KEY)
        self._kek = kek_provider

    def encrypt(self, plaintext: dict) -> tuple[bytes, bytes]:
        dek = Fernet.generate_key()
        ciphertext = Fernet(dek).encrypt(json.dumps(plaintext).encode())
        dek_enc = self._kek.encrypt_dek(dek)
        return ciphertext, dek_enc

    def decrypt(self, ciphertext: bytes, dek_enc: bytes) -> dict:
        dek = self._kek.decrypt_dek(dek_enc)
        plaintext = Fernet(dek).decrypt(ciphertext)
        return json.loads(plaintext)
