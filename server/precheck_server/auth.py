"""Authentication and authorization middleware."""

import ipaddress
from typing import Callable, List, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from precheck_server.config import AuthConfig


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for API key and IP-based authentication."""

    # Paths that don't require authentication
    EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app, auth_config: AuthConfig):
        super().__init__(app)
        self.auth_config = auth_config
        self._valid_keys = {key.key for key in auth_config.api_keys}
        self._allowed_networks = self._parse_allowed_ips(auth_config.allowed_ips)

    def _parse_allowed_ips(
        self, allowed_ips: List[str]
    ) -> List[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        """Parse IP addresses and CIDR notation."""
        networks = []
        for ip_str in allowed_ips:
            try:
                # Try as network (CIDR)
                networks.append(ipaddress.ip_network(ip_str, strict=False))
            except ValueError:
                # Try as single IP
                try:
                    addr = ipaddress.ip_address(ip_str)
                    # Convert to /32 or /128 network
                    prefix = 32 if isinstance(addr, ipaddress.IPv4Address) else 128
                    networks.append(ipaddress.ip_network(f"{ip_str}/{prefix}"))
                except ValueError:
                    pass
        return networks

    def _is_ip_allowed(self, client_ip: str) -> bool:
        """Check if client IP is in allowed list."""
        if not self._allowed_networks:
            return True  # Empty list = allow all

        try:
            addr = ipaddress.ip_address(client_ip)
            return any(addr in network for network in self._allowed_networks)
        except ValueError:
            return False

    def _extract_api_key(self, request: Request) -> Optional[str]:
        """Extract API key from request headers."""
        # Try Authorization header first
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]

        # Try X-API-Key header
        return request.headers.get("X-API-Key")

    async def dispatch(self, request: Request, call_next: Callable):
        """Process the request through auth checks."""
        # Skip auth for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Check IP allowlist
        client_ip = request.client.host if request.client else "unknown"
        if not self._is_ip_allowed(client_ip):
            return JSONResponse(
                status_code=403,
                content={"message": f"Forbidden: IP {client_ip} not allowed"},
            )

        # Check API key if required
        if self.auth_config.required:
            api_key = self._extract_api_key(request)
            if not api_key:
                return JSONResponse(
                    status_code=401,
                    content={"message": "Unauthorized: API key required"},
                )
            if api_key not in self._valid_keys:
                return JSONResponse(
                    status_code=401,
                    content={"message": "Unauthorized: Invalid API key"},
                )

        return await call_next(request)
