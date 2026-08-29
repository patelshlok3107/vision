import ipaddress
import re
import socket
from urllib.parse import urlparse, urlunparse


# ---------------------------------------------------------------------------
# SSRF Protection
# ---------------------------------------------------------------------------

PRIVATE_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

BLOCKED_HOSTS = {
    "localhost", "metadata.google.internal", "metadata.google",
    "169.254.169.254",  # AWS / GCP metadata
}

# Cloud metadata endpoints
METADATA_IPS = {"169.254.169.254", "fd00:ec2::254"}


def _is_private_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return any(ip in net for net in PRIVATE_NETS)
    except ValueError:
        return False


def validate_url_for_crawl(raw_url: str) -> tuple[bool, str]:
    """
    Validate URL for safe crawling.
    Returns (ok, error). Checks SSRF, private nets, localhost, scheme.
    """
    if not raw_url or len(raw_url) > 2000:
        return False, "URL too long or empty"
    raw_url = raw_url.strip()
    if not re.match(r"^https?://", raw_url, re.IGNORECASE):
        return False, "Only http:// and https:// URLs are allowed"
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return False, "Invalid URL"
    host = (parsed.hostname or "").lower().strip()
    if not host:
        return False, "Invalid URL host"
    if host in BLOCKED_HOSTS:
        return False, "Crawling localhost/internal hosts is not allowed"
    if host.endswith(".internal") or host.endswith(".local"):
        return False, "Internal host not allowed"
    # Block IP literals that are private
    try:
        ip = ipaddress.ip_address(host)
        if any(ip in net for net in PRIVATE_NETS):
            return False, "Private IP addresses are not allowed"
    except ValueError:
        pass
    # DNS resolution check for private IPs (best-effort)
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in infos:
            ip_str = sockaddr[0]
            if _is_private_ip(ip_str) or ip_str in METADATA_IPS:
                return False, "Host resolves to a private or metadata IP (SSRF blocked)"
    except socket.gaierror:
        return False, "Host could not be resolved"
    except Exception:
        pass
    return True, ""


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    parsed = urlparse(url)
    # Lowercase host
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), netloc, path, parsed.params, parsed.query, ""))


def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def log_admin_activity(admin_username: str, action: str, request=None, target_type="", target_id="", status="success", details: dict | None = None):
    try:
        from .models import AdminActivity
        ip = None
        if request is not None:
            xff = request.META.get("HTTP_X_FORWARDED_FOR")
            if xff:
                ip = xff.split(",")[0].strip()
            else:
                ip = request.META.get("REMOTE_ADDR")
        AdminActivity.objects.create(
            admin_username=admin_username,
            action=action,
            target_type=target_type,
            target_id=str(target_id)[:100],
            status=status,
            details=details or {},
            ip_address=ip if ip and _is_valid_ip(ip) else None,
        )
    except Exception:
        pass


def _is_valid_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except Exception:
        return False
