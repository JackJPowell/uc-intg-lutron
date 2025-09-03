"""Discovery module for Zeroconf protocol."""

import asyncio
from dataclasses import dataclass
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf, AsyncServiceInfo
from zeroconf import ServiceStateChange, IPVersion


@dataclass
class ZeroconfService:
    address: str


class ZeroconfScanner:
    def __init__(self, service_type="_lutron._tcp.local."):
        self.service_type = service_type
        self.found_services = [ZeroconfService]

    async def on_service_state_change(
        self, zeroconf, service_type, name, state_change, **kwargs
    ):
        if state_change is ServiceStateChange.Added:
            info = AsyncServiceInfo(service_type, name)
            await info.async_request(zeroconf, timeout=2000)
            if info.parsed_addresses():
                self.found_services.append(
                    ZeroconfService(
                        address=info.parsed_addresses(version=IPVersion.V4Only)[0]
                    )
                )

    async def scan(self, timeout=2):
        self.found_services = []
        async with AsyncZeroconf() as azc:

            def handler(**kwargs):
                asyncio.create_task(self.on_service_state_change(**kwargs))

            browser = AsyncServiceBrowser(
                azc.zeroconf, self.service_type, handlers=[handler]
            )
            await asyncio.sleep(timeout)
        return self.found_services
