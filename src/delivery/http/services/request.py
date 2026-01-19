import ipaddress
import logging
from dataclasses import dataclass

from pydantic_settings import BaseSettings
from starlette.requests import Request

logger = logging.getLogger(__name__)


class RequestInfoServiceSettings(BaseSettings):
    number_of_proxies: int = 0
    """Number of proxies in front of the application. Used to determine the real client IP address."""

    ip_header: str = "x-forwarded-for"
    """Header to look for the client IP address when behind proxies."""

    user_agent_header: str = "user-agent"
    """Header to look for the user agent string."""


@dataclass(kw_only=True)
class RequestInfoService:
    _settings: RequestInfoServiceSettings

    def get_user_agent(self, request: Request) -> str:
        return request.headers.get(self._settings.user_agent_header, "")

    def get_user_ip(self, request: Request) -> str | None:
        xff = request.headers.get(self._settings.ip_header)

        if self._settings.number_of_proxies == 0 or xff is None:
            client = request.client
            remote_address = client[0] if client else None

            # Validate that remote_address is a valid IP, otherwise return None
            if remote_address and self._is_valid_ip(remote_address):
                return remote_address

            logger.warning("Remote address is not a valid IP: %s", remote_address)
            return None

        addresses = xff.split(",")
        client_address = addresses[-min(self._settings.number_of_proxies, len(addresses))]
        return client_address.strip()

    def _is_valid_ip(self, address: str) -> bool:
        try:
            ipaddress.ip_address(address)
        except ValueError:
            return False
        else:
            return True
