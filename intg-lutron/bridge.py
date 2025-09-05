"""
This module implements the Lutron communication of the Remote Two/3 integration driver.

"""

import asyncio
import logging
from dataclasses import dataclass
from asyncio import AbstractEventLoop
from enum import StrEnum, IntEnum
import os
import sys
from typing import Any, ParamSpec, TypeVar

from pylutron_caseta.smartbridge import Smartbridge
from pyee.asyncio import AsyncIOEventEmitter
from ucapi.media_player import Attributes as MediaAttr
from ucapi import EntityTypes
from config import LutronConfig, create_entity_id
from const import LutronLightInfo, LutronSceneInfo

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
class LutronCoverInfo:
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
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            path = os.environ["UC_DATA_HOME"]
        else:
            path = "./data"
        self._loop: AbstractEventLoop = loop or asyncio.get_running_loop()
        self.events = AsyncIOEventEmitter(self._loop)
        self._is_connected: bool = False
        self._config: LutronConfig | None = config
        self._lutron_smart_hub: Smartbridge = Smartbridge.create_tls(
            self._config.address,
            f"{path}/caseta.key",
            f"{path}/caseta.crt",
            f"{path}/caseta-bridge.crt",
        )
        self._connection_attempts: int = 0
        self._state: PowerState = PowerState.OFF
        self._features: dict = {}
        self._lights: list = [LutronLightInfo]
        self._covers: list = [LutronCoverInfo]
        self._scenes: list = [LutronSceneInfo]
        self._scene: LutronSceneInfo | None = None

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
        return self._config.identifier

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
        return "ON" if self._is_connected else "OFF"

    @property
    def attributes(self) -> dict[str, any]:
        """Return the device attributes."""
        updated_data = {
            MediaAttr.STATE: self.state,
        }
        return updated_data

    @property
    def lights(self) -> list[Any]:
        """Return the list of light entities."""
        return self._lights

    @property
    def covers(self) -> list[Any]:
        """Return the list of cover entities."""
        return self._covers

    @property
    def scenes(self) -> list[Any]:
        """Return the list of scene entities."""
        return self._scenes

    @property
    def scene(self) -> str | None:
        """Return the current scene."""
        return self._scene.name if self._scene else None

    @property
    def is_connected(self) -> bool:
        """Return if the device is connected."""
        return self._is_connected

    async def connect(self) -> None:
        """Establish connection to the Lutron device."""
        if self._lutron_smart_hub.logged_in:
            return

        _LOG.debug("[%s] Connecting to device", self.log_id)
        self.events.emit(EVENTS.CONNECTING, self.device_config.identifier)
        await self._connect_setup()

    async def _connect_setup(self) -> None:
        try:
            await self._connect()
        except asyncio.CancelledError:
            pass
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Could not connect: %s", self.log_id, err)
        finally:
            _LOG.debug("[%s] Connect setup finished", self.log_id)

        self.events.emit(EVENTS.CONNECTED, self.device_config.identifier)
        _LOG.debug("[%s] Connected", self.log_id)

        self._update_lights()
        for light in self._lights:
            self._lutron_smart_hub.add_subscriber(light.device_id, self._update_lights)
        self._update_scenes()

    async def _connect(self) -> None:
        """Connect to the device."""
        _LOG.debug(
            "[%s] Connecting to TVWS device at IP address: %s",
            self.log_id,
            self.address,
        )
        try:
            # await self._lutron_smart_hub.close()
            await self._lutron_smart_hub.connect()
            self._is_connected = True
            self._state = PowerState.ON
            _LOG.info("[%s] Connected to device", self.log_id)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Connection error: %s", self.log_id, err)

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        _LOG.debug("[%s] Disconnecting from device", self.log_id)
        await self._lutron_smart_hub.close()
        self._is_connected = False
        self._state = PowerState.OFF
        self.events.emit(EVENTS.DISCONNECTED, self.device_config.identifier)

    def _update_lights(self) -> None:
        update = {}
        try:
            self._lights = self.get_lights()

            for entity in self._lights:
                update = {}
                update["state"] = "ON" if entity.current_state > 0 else "OFF"
                update["brightness"] = int(entity.current_state * 255 / 100)

                self.events.emit(
                    EVENTS.UPDATE,
                    create_entity_id(
                        self.device_config.identifier,
                        entity.device_id,
                        EntityTypes.LIGHT,
                    ),
                    update,
                )

        except Exception:  # pylint: disable=broad-exception-caught
            _LOG.exception("[%s] App list: protocol error", self.log_id)

    def _update_scenes(self) -> None:
        update = {}
        update["state"] = self.state

        try:
            self._scenes = self.get_scenes()
            update["source_list"] = [scene.name for scene in self._scenes]

            self.events.emit(
                EVENTS.UPDATE,
                create_entity_id(
                    self.device_config.identifier,
                    "0",
                    EntityTypes.MEDIA_PLAYER,
                ),
                update,
            )

        except Exception:  # pylint: disable=broad-exception-caught
            _LOG.exception("[%s] App list: protocol error", self.log_id)

    def get_lights(self) -> list[Any]:
        """Return the list of light entities."""
        lights = self._lutron_smart_hub.get_devices_by_domain("light")
        light_list = []
        for entity in lights:
            light_list.append(
                LutronLightInfo(
                    device_id=entity.get("device_id"),
                    current_state=entity.get("current_state"),
                    type=entity.get("type"),
                    name=entity.get("name"),
                    model=entity.get("model"),
                )
            )
        return light_list

    def get_scenes(self) -> list[Any]:
        """Return the list of scene entities."""
        scenes = self._lutron_smart_hub.get_scenes()
        scene_list = []
        for scene in scenes.values():
            scene_list.append(
                LutronSceneInfo(
                    scene_id=scene.get("scene_id"),
                    name=scene.get("name"),
                )
            )
        return scene_list

    async def activate_scene(self, scene_id: str) -> None:
        """Activate a scene."""
        scene: LutronSceneInfo = next(
            (s for s in self.scenes if s.scene_id == scene_id), None
        )
        if scene is None:
            _LOG.error("[%s] Scene %s not found", self.log_id, scene_id)
            return
        try:
            await self._lutron_smart_hub.activate_scene(scene.scene_id)
            self._scene = scene
            self.events.emit(
                EVENTS.UPDATE,
                create_entity_id(
                    self.device_config.identifier,
                    "0",
                    EntityTypes.MEDIA_PLAYER,
                ),
                {"source": scene.name},
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error(
                "[%s] Error activating scene %s: %s", self.log_id, scene.name, err
            )

    async def turn_on_light(self, light_id: str, brightness: int = None) -> None:
        """Turn on a light with a specific brightness."""
        try:
            if brightness is not None:
                await self._lutron_smart_hub.set_value(light_id, brightness)
            else:
                await self._lutron_smart_hub.turn_on(light_id)
                self.events.emit(
                    EVENTS.UPDATE,
                    create_entity_id(
                        self._config.identifier,
                        light_id,
                        EntityTypes.LIGHT,
                    ),
                    {"state": "ON", "brightness": brightness},
                )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Error turning on light %s: %s", self.log_id, light_id, err)

    async def turn_off_light(self, light_id: str) -> None:
        """Turn off a light."""
        try:
            await self._lutron_smart_hub.turn_off(light_id)
            self.events.emit(
                EVENTS.UPDATE,
                create_entity_id(
                    self._config.identifier,
                    light_id,
                    EntityTypes.LIGHT,
                ),
                {"state": "OFF", "brightness": 0},
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error(
                "[%s] Error turning off light %s: %s", self.log_id, light_id, err
            )

    async def toggle_light(self, light_id: str) -> None:
        """Toggle a light."""
        try:
            is_on = self._lutron_smart_hub.is_on(light_id)
            if is_on:
                await self._lutron_smart_hub.turn_off(light_id)
            else:
                await self._lutron_smart_hub.turn_on(light_id)
            self.events.emit(
                EVENTS.UPDATE,
                create_entity_id(
                    self._config.identifier,
                    light_id,
                    EntityTypes.LIGHT,
                ),
                {
                    "state": "ON" if not is_on else "OFF",
                    "brightness": 100 if not is_on else 0,
                },
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Error toggling light %s: %s", self.log_id, light_id, err)
