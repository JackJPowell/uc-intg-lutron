"""
This module implements the Lutron constants for the Remote Two/3 integration driver.
"""

from dataclasses import dataclass


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
