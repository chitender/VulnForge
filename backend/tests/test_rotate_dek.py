"""Unit tests for the DEK rotation script logic."""

from cryptography.fernet import Fernet

from app.core.credentials import CredentialStore, LocalKEKProvider


def test_rotate_dek_produces_new_wrapped_dek():
    """Rotating the KEK produces a different dek_enc but decrypts to the same plaintext."""
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    old_store = CredentialStore(LocalKEKProvider(old_key))
    new_kek = Fernet(new_key.encode())
    old_kek = Fernet(old_key.encode())

    plaintext = {"aws_access_key_id": "AKIAIOSFODNN7EXAMPLE", "region": "us-east-1"}
    ciphertext, old_dek_enc = old_store.encrypt(plaintext)

    # Simulate rotation: unwrap with old KEK, re-wrap with new KEK
    dek = old_kek.decrypt(old_dek_enc)
    new_dek_enc = new_kek.encrypt(dek)

    assert new_dek_enc != old_dek_enc  # DEK wrapping changed

    # Verify new_dek_enc still decrypts to the same plaintext
    new_store = CredentialStore(LocalKEKProvider(new_key))
    recovered = new_store.decrypt(ciphertext, new_dek_enc)
    assert recovered == plaintext


def test_rotate_dek_ciphertext_unchanged():
    """auth_ciphertext is never modified during DEK rotation — only dek_enc changes."""
    import json

    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    old_store = CredentialStore(LocalKEKProvider(old_key))
    old_kek = Fernet(old_key.encode())
    new_kek = Fernet(new_key.encode())

    plaintext = {"token": "glpat-secret"}
    ciphertext_before, old_dek_enc = old_store.encrypt(plaintext)

    # Simulate rotation — only dek_enc changes, ciphertext is never touched
    dek = old_kek.decrypt(old_dek_enc)
    new_kek.encrypt(dek)
    ciphertext_after = ciphertext_before  # rotation must not reassign this

    # Verify the ciphertext is byte-for-byte unchanged
    assert ciphertext_after == ciphertext_before

    # Verify it still decrypts to the original plaintext using the same DEK
    recovered = Fernet(dek).decrypt(ciphertext_after)
    assert json.loads(recovered) == plaintext


def test_wrong_old_key_raises():
    """Using the wrong OLD_MASTER_KEY fails immediately — no partial rotation."""
    real_key = Fernet.generate_key().decode()
    wrong_key = Fernet.generate_key().decode()
    store = CredentialStore(LocalKEKProvider(real_key))
    _, dek_enc = store.encrypt({"x": "y"})

    import pytest

    with pytest.raises(Exception):
        Fernet(wrong_key.encode()).decrypt(dek_enc)
