"""
SSRF-prevention validator for user-supplied registry URLs.

Blocks:
  - Non-HTTPS schemes
  - Userinfo in URL (user@host)
  - Loopback:      127.0.0.0/8, ::1
  - Link-local:    169.254.0.0/16, fe80::/10
  - RFC1918:       10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
  - IPv6 ULA:      fc00::/7
  - Unspecified:   0.0.0.0

Apply at BOTH schema-validation time (RegistryCreate) and before each outbound request.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
]

# Minimal valid hostname: no path, no scheme, no port required
_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?(:[0-9]+)?$")


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in _BLOCKED_NETWORKS)


def validate_registry_url(registry_url: str) -> str:
    """Validate a registry hostname (without scheme).

    Accepts  :  myregistry.example.com  OR  myregistry.example.com:5000
    Rejects  :  any URL with scheme, userinfo, private/loopback IPs.

    Returns the validated hostname string.
    Raises   :  ValueError on any violation.
    """
    if not registry_url or not registry_url.strip():
        raise ValueError("registry_url must not be empty")

    # Reject if caller accidentally included a scheme
    if "://" in registry_url:
        parsed = urlparse(registry_url)
        if parsed.scheme and parsed.scheme.lower() != "https":
            raise ValueError(f"registry_url must use HTTPS, got scheme '{parsed.scheme}'")
        if parsed.username or parsed.password:
            raise ValueError("registry_url must not contain userinfo (user@host)")
        hostname = parsed.hostname or ""
    else:
        # Treat as bare hostname[:port]
        if "@" in registry_url:
            raise ValueError("registry_url must not contain userinfo (user@host)")
        hostname = registry_url.split(":")[0]

    if not hostname:
        raise ValueError("registry_url contains no resolvable hostname")

    # Resolve DNS and check every returned address
    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"registry_url hostname '{hostname}' does not resolve: {exc}") from exc

    for _, _, _, _, sockaddr in results:
        ip = str(sockaddr[0])
        if _is_blocked_ip(ip):
            raise ValueError(
                f"registry_url hostname '{hostname}' resolves to a blocked address ({ip}). "
                "Loopback, link-local (169.254.x.x), and RFC1918 addresses are not permitted."
            )

    return registry_url
