import ipaddress
import socket
from urllib.parse import urlparse
from novora.core.exceptions import SSRFSecurityError

FORBIDDEN_SUBNETS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC1918 Private
    ipaddress.ip_network("172.16.0.0/12"),    # RFC1918 Private
    ipaddress.ip_network("192.168.0.0/16"),   # RFC1918 Private
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local / Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("100.64.0.0/10"),    # Carrier-grade NAT
    ipaddress.ip_network("0.0.0.0/8"),        # Current network
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 Unique local
    ipaddress.ip_network("fe80::/10"),        # IPv6 Link-local
]

FORBIDDEN_HOSTNAMES = {"localhost", "metadata.google.internal", "instance-data"}

def validate_destination_endpoint(url: str, allow_private: bool = False) -> None:
    """Validates remote destination URL to prevent SSRF vulnerabilities.

    Rejects non-HTTP(S) schemes, loopback, private subnets, and cloud metadata addresses.
    """
    if not url or not isinstance(url, str):
        raise SSRFSecurityError(str(url), "URL must be a non-empty string.")

    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise SSRFSecurityError(url, f"Forbidden scheme '{scheme}'. Only HTTP and HTTPS are permitted.")

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        raise SSRFSecurityError(url, "URL missing valid hostname.")

    if hostname in FORBIDDEN_HOSTNAMES:
        raise SSRFSecurityError(url, f"Forbidden hostname '{hostname}'.")

    if allow_private:
        return

    # Check if hostname is direct IP literal
    try:
        ip_obj = ipaddress.ip_address(hostname)
        ips = [ip_obj]
    except ValueError:
        # Resolve hostname to IPs
        try:
            addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if scheme == "https" else 80))
            ips = [ipaddress.ip_address(item[4][0]) for item in addr_info]
        except (socket.gaierror, IndexError):
            # If DNS fails to resolve during test or offline, check for obvious loopback/local patterns
            if "local" in hostname or "internal" in hostname:
                raise SSRFSecurityError(url, "Hostname resolves to internal network pattern.")
            ips = []

    for ip in ips:
        if ip.is_loopback:
            raise SSRFSecurityError(url, f"IP {ip} is a loopback address.")
        if ip.is_link_local:
            raise SSRFSecurityError(url, f"IP {ip} is a link-local / cloud metadata address.")
        if ip.is_private:
            raise SSRFSecurityError(url, f"IP {ip} is in a private RFC1918 subnet.")
        for subnet in FORBIDDEN_SUBNETS:
            if ip in subnet:
                raise SSRFSecurityError(url, f"IP {ip} belongs to blocked subnet {subnet}.")
