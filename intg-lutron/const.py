"""
This module implements the Lutron constants for the Remote Two/3 integration driver.
"""

from dataclasses import dataclass


@dataclass
class LutronConfig:
    """Lutron device configuration."""

    identifier: str
    """Unique identifier of the device. (MAC Address)"""
    address: str
    """IP Address of device."""
    name: str
    """Name of the device."""
    model: str
    """Model name of the device."""
    ca_cert: str = ""
    """CA certificate (caseta-bridge.crt) as text."""
    cert: str = ""
    """Client certificate (caseta.crt) as text."""
    key: str = ""
    """Private key (caseta.key) as text."""


@dataclass
class LutronLightInfo:
    device_id: str
    current_state: int
    type: str
    name: str
    model: str


@dataclass
class LutronCoverInfo:
    device_id: str
    current_state: int
    type: str
    name: str
    model: str


@dataclass
class LutronSceneInfo:
    scene_id: str
    name: str
