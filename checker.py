import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def validate_url(url: str) -> str:
    """Validate that a URL uses http or https and has a valid hostname."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string.")
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Invalid HTTP/HTTPS URL: {url}")
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain embedded credentials.")
    return url.strip()


def validate_https_url(url: str) -> str:
    """Validate an HTTPS-only URL for endpoints that receive alert data."""
    clean_url = validate_url(url)
    if urllib.parse.urlparse(clean_url).scheme != "https":
        raise ValueError("URL must use https.")
    return clean_url


def check_http_status(url: str, timeout_sec: float = 5.0) -> tuple[bool, int]:
    """Return (is_up, status_code). Marks status >= 500 or network errors as down."""
    clean_url = validate_url(url)
    req = urllib.request.Request(
        clean_url,
        headers={"User-Agent": "bsloopstudio-uptime/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            code = resp.getcode()
            return (code < 500, code)
    except urllib.error.HTTPError as err:
        return (err.code < 500, err.code)
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        return (False, 0)


def get_ssl_days_left(hostname: str, port: int = 443, timeout_sec: float = 5.0) -> int:
    """Return remaining days until the TLS certificate expires. Negative means expired."""
    if not isinstance(hostname, str) or not hostname.strip():
        raise ValueError("Hostname must be a non-empty string.")
    clean_host = hostname.strip()
    context = ssl.create_default_context()
    with socket.create_connection((clean_host, port), timeout=timeout_sec) as sock:
        with context.wrap_socket(sock, server_hostname=clean_host) as ssock:
            cert = ssock.getpeercert()
    if not cert or "notAfter" not in cert:
        raise ValueError(f"No certificate expiry date found for {clean_host}")
    expiry = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (expiry - now).days


def is_internet_online(probe_url: str = "https://1.1.1.1", timeout_sec: float = 3.0) -> bool:
    """Verify local internet connectivity before sending customer down alerts."""
    is_up, _ = check_http_status(probe_url, timeout_sec=timeout_sec)
    return is_up
