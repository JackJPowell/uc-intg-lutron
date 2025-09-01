"""
This module implements the Lutron communication of the Remote Two/3 integration driver.

"""

import asyncio
import logging
from dataclasses import dataclass
from asyncio import AbstractEventLoop
from enum import StrEnum, IntEnum
from typing import Any, ParamSpec, TypeVar

from pylutron_caseta.smartbridge import Smartbridge
from pyee.asyncio import AsyncIOEventEmitter
from ucapi.media_player import Attributes as MediaAttr
from config import LutronConfig

_LOG = logging.getLogger(__name__)


class EVENTS(IntEnum):
    """Internal driver events."""

    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2
    PAIRED = 3
    ERROR = 4
    UPDATE = 5


_LutronDeviceT = TypeVar("_LutronDeviceT", bound="LutronConfig")
_P = ParamSpec("_P")


@dataclass
class LutronLightInfo:
    device_id: str
    current_state: int
    type: str
    name: str


class PowerState(StrEnum):
    """Playback state for companion protocol."""

    OFF = "OFF"
    ON = "ON"
    STANDBY = "STANDBY"


class SmartHub:
    """Representing a Lutron Smart Hub Device."""

    def __init__(
        self, config: LutronConfig, loop: AbstractEventLoop | None = None
    ) -> None:
        """Create instance."""
        self._loop: AbstractEventLoop = loop or asyncio.get_running_loop()
        self.events = AsyncIOEventEmitter(self._loop)
        self._is_connected: bool = False
        self._config: LutronConfig | None = config
        self._lutron_smart_hub: Smartbridge = Smartbridge.create_tls(
            self._config.address, "caseta.key", "caseta.crt", "caseta-bridge.crt"
        )
        self._connection_attempts: int = 0
        self._state: PowerState = PowerState.OFF
        self._features: dict = {}
        self.entities: list = [LutronLightInfo]

    @property
    def device_config(self) -> LutronConfig:
        """Return the device configuration."""
        return self._config

    @property
    def identifier(self) -> str:
        """Return the device identifier."""
        if not self._config.identifier:
            raise ValueError("Instance not initialized, no identifier available")
        return self._config.identifier

    @property
    def log_id(self) -> str:
        """Return a log identifier."""
        return self._config.name if self._config.name else self._config.identifier

    @property
    def name(self) -> str:
        """Return the device name."""
        return self._config.name

    @property
    def address(self) -> str | None:
        """Return the optional device address."""
        return self._config.address

    @property
    def state(self) -> PowerState | None:
        """Return the device state."""
        return self._state.upper()

    @property
    def attributes(self) -> dict[str, any]:
        """Return the device attributes."""
        updated_data = {
            MediaAttr.STATE: self.state,
        }
        return updated_data

    async def connect(self) -> None:
        """Establish connection to the AVR."""
        if self.state != PowerState.OFF:
            return

        _LOG.debug("[%s] Connecting to device", self.log_id)
        self.events.emit(EVENTS.CONNECTING, self._config.identifier)
        await self._connect_setup()

    async def _connect_setup(self) -> None:
        try:
            await self._connect()

            if self.state != PowerState.OFF:
                _LOG.debug("[%s] Device is alive", self.log_id)
                self.events.emit(
                    EVENTS.UPDATE, self._config.identifier, {"state": self.state}
                )
            else:
                _LOG.debug("[%s] Device is not alive", self.log_id)
                self.events.emit(
                    EVENTS.UPDATE,
                    self._config.identifier,
                    {"state": PowerState.OFF},
                )
        except asyncio.CancelledError:
            pass
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Could not connect: %s", self.log_id, err)
        finally:
            _LOG.debug("[%s] Connect setup finished", self.log_id)

        self.events.emit(EVENTS.CONNECTED, self._config.identifier)
        _LOG.debug("[%s] Connected", self.log_id)

        await self._update_attributes()

    async def _connect(self) -> None:
        """Connect to the device."""
        _LOG.debug(
            "[%s] Connecting to TVWS device at IP address: %s",
            self.log_id,
            self.address,
        )
        try:
            await self._lutron_smart_hub.connect()
            self._is_connected = True
            self._state = PowerState.ON
            _LOG.info("[%s] Connected to device", self.log_id)
        except Exception as err:
            _LOG.error("[%s] Connection error: %s", self.log_id, err)
            self._state = PowerState.OFF

    async def _update_attributes(self) -> None:
        _LOG.debug("[%s] Updating app list", self.log_id)
        update = {}

        try:
            lights = self._lutron_smart_hub.get_devices_by_domain("light")

        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Error retrieving status: %s", self.log_id, err)

        try:
            for entity in lights:
                self.entities.append(
                    LutronLightInfo(
                        device_id=entity.device_id,
                        current_state=entity.current_state,
                        type=entity.type,
                        name=entity.name,
                    )
                )
                update["state"] = entity.current_state
                self.events.emit(EVENTS.UPDATE, self._config.identifier, update)

        except Exception:  # pylint: disable=broad-exception-caught
            _LOG.exception("[%s] App list: protocol error", self.log_id)

    async def send_command(self, command: str, *args: Any, **kwargs: Any) -> str:
        """Send a command to the Bridge."""
        update = {}
        res = ""
        try:
            _LOG.debug(
                "[%s] Sending command: %s, args: %s, kwargs: %s",
                self.log_id,
                command,
                args,
                kwargs,
            )
            match command:
                case "powerOn":
                    pass

            self.events.emit(EVENTS.UPDATE, self._config.identifier, update)
            return res
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error(
                "[%s] Error sending command %s: %s",
                self.log_id,
                command,
                err,
            )
            raise Exception(err) from err  # pylint: disable=broad-exception-raised
