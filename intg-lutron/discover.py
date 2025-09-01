"""Discovery module for SDDP protocol."""

from dataclasses import dataclass
from typing import Iterable, Optional
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf


@dataclass
class ZeroconfResponseInfo:
    """
    This class is used to store information about a response received from the Zeroconf protocol.
    It contains the datagram and the address of the sender.
    """

    def __init__(self, address=None, name=None):
        self.address = address
        self.name = name

    def __repr__(self):
        return f"ZeroconfResponseInfo(name={self.name}, address={self.address})"


class MyListener(ServiceListener):
    """
    This class is used to store information about a response received from the Zeroconf protocol.
    It contains the datagram and the address of the sender.
    """

    def __init__(self):
        self.datagrams: list = []

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"Service {name} updated")

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"Service {name} removed")

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        print(f"Service {name} added, service info: {info}")


class ZeroconfDiscovery:
    """
    Discover Lutron devices using Zeroconf.
    """

    def __init__(self):
        self.zeroconf = Zeroconf()
        self.listener = MyListener()
        self.browser = ServiceBrowser(
            self.zeroconf, "_lutron._tcp.local.", self.listener, delay=2
        )
        self.discovered: list[ZeroconfResponseInfo] = []

    def start(self):
        try:
            pass
        finally:
            self.zeroconf.close()

        return self.discovered
