from cryptography.fernet import Fernet
import pytest

from app.core.credentials import CredentialStore, LocalKEKProvider

MASTER_KEY = Fernet.generate_key().decode()


def make_store() -> CredentialStore:
    return CredentialStore(LocalKEKProvider(MASTER_KEY))


def test_encrypt_returns_two_byte_blobs():
    store = make_store()
    ciphertext, dek_enc = store.encrypt({"username": "user", "password": "s3cr3t"})
    assert isinstance(ciphertext, bytes) and len(ciphertext) > 0
    assert isinstance(dek_enc, bytes) and len(dek_enc) > 0


def test_decrypt_roundtrip():
    store = make_store()
    plaintext = {"token": "ghp_abc123", "region": "us-east-1"}
    ciphertext, dek_enc = store.encrypt(plaintext)
    assert store.decrypt(ciphertext, dek_enc) == plaintext


def test_each_encrypt_produces_unique_dek():
    store = make_store()
    _, dek1 = store.encrypt({"username": "user"})
    _, dek2 = store.encrypt({"username": "user"})
    assert dek1 != dek2


def test_wrong_kek_raises():
    store1 = make_store()
    store2 = CredentialStore(LocalKEKProvider(Fernet.generate_key().decode()))
    ciphertext, dek_enc = store1.encrypt({"x": "y"})
    with pytest.raises(Exception):
        store2.decrypt(ciphertext, dek_enc)


def test_plaintext_not_in_ciphertext():
    store = make_store()
    secret = "super_secret_password_12345"
    ciphertext, _ = store.encrypt({"password": secret})
    assert secret.encode() not in ciphertext
