"""Tests for SSRF-prevention URL validator."""
import pytest
from unittest.mock import patch

from app.core.url_validator import validate_registry_url


def _mock_resolve(ip: str):
    """Return a mock getaddrinfo result that resolves to `ip`."""
    return [(None, None, None, None, (ip, 0))]


def test_valid_public_hostname():
    with patch("socket.getaddrinfo", return_value=_mock_resolve("34.120.0.1")):
        result = validate_registry_url("registry.example.com")
    assert result == "registry.example.com"


def test_valid_hostname_with_port():
    with patch("socket.getaddrinfo", return_value=_mock_resolve("34.120.0.1")):
        result = validate_registry_url("registry.example.com:5000")
    assert result == "registry.example.com:5000"


def test_blocks_loopback_127():
    with patch("socket.getaddrinfo", return_value=_mock_resolve("127.0.0.1")):
        with pytest.raises(ValueError, match="blocked address"):
            validate_registry_url("localhost")


def test_blocks_cloud_metadata_169_254():
    with patch("socket.getaddrinfo", return_value=_mock_resolve("169.254.169.254")):
        with pytest.raises(ValueError, match="blocked address"):
            validate_registry_url("metadata.internal")


def test_blocks_rfc1918_10():
    with patch("socket.getaddrinfo", return_value=_mock_resolve("10.0.0.1")):
        with pytest.raises(ValueError, match="blocked address"):
            validate_registry_url("internal-registry.corp")


def test_blocks_rfc1918_192_168():
    with patch("socket.getaddrinfo", return_value=_mock_resolve("192.168.1.100")):
        with pytest.raises(ValueError, match="blocked address"):
            validate_registry_url("my-registry.local")


def test_blocks_rfc1918_172_16():
    with patch("socket.getaddrinfo", return_value=_mock_resolve("172.16.0.1")):
        with pytest.raises(ValueError, match="blocked address"):
            validate_registry_url("staging-registry.internal")


def test_blocks_userinfo():
    with pytest.raises(ValueError, match="userinfo"):
        validate_registry_url("user@registry.example.com")


def test_blocks_non_https_scheme():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_registry_url("http://registry.example.com")


def test_blocks_empty():
    with pytest.raises(ValueError):
        validate_registry_url("")


def test_accepts_https_scheme():
    with patch("socket.getaddrinfo", return_value=_mock_resolve("34.120.0.1")):
        result = validate_registry_url("https://registry.example.com")
    assert result == "https://registry.example.com"


def test_blocks_dns_failure():
    import socket as _socket
    with patch("socket.getaddrinfo", side_effect=_socket.gaierror("NXDOMAIN")):
        with pytest.raises(ValueError, match="does not resolve"):
            validate_registry_url("nonexistent.invalid")
