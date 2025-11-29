"""
This module implements the Lutron constants for the Remote Two/3 integration driver.
"""

from dataclasses import dataclass


@dataclass
class LutronDevice:
    """Lutron device configuration."""

    identifier: str
    """Unique identifier of the device. (MAC Address)"""
    address: str
    """IP Address of device."""
    name: str
    """Name of the device."""
    model: str
    """Model name of the device."""


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
