"""
This module implements the Lutron communication of the Remote Two/3 integration driver.

"""

import logging
import os
import sys
from asyncio import AbstractEventLoop
from typing import Any

from const import LutronCoverInfo, LutronDevice, LutronLightInfo, LutronSceneInfo
from pylutron_caseta.smartbridge import Smartbridge
from ucapi import EntityTypes
from ucapi.light import Attributes as LightAttr
from ucapi.media_player import Attributes as MediaAttr
from ucapi_framework import ExternalClientDevice, create_entity_id
from ucapi_framework.device import DeviceEvents

_LOG = logging.getLogger(__name__)


class SmartHub(ExternalClientDevice):
    """Representing a Lutron Smart Hub Device."""

    def __init__(
        self,
        config: LutronDevice,
        loop: AbstractEventLoop | None = None,
        config_manager=None,
    ) -> None:
        """Create instance."""
        super().__init__(
            config,
            loop=loop,
            watchdog_interval=30,
            reconnect_delay=5,
            max_reconnect_attempts=0,  # Infinite retries
        )

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            path = os.environ["UC_DATA_HOME"]
        else:
            path = "./data"

        self._key_path = f"{path}/caseta.key"
        self._cert_path = f"{path}/caseta.crt"
        self._bridge_cert_path = f"{path}/caseta-bridge.crt"
        self._lutron_smart_hub: Smartbridge | None = None
        self._lights: list[LutronLightInfo] = []
        self._covers: list[LutronCoverInfo] = []
        self._scenes: list[LutronSceneInfo] = []
        self._scene: LutronSceneInfo | None = None

    @property
    def device_config(self) -> LutronDevice:
        """Return the device configuration."""
        return self._device_config

    @property
    def identifier(self) -> str:
        """Return the device identifier."""
        return self.device_config.identifier

    @property
    def log_id(self) -> str:
        """Return a log identifier."""
        return self.device_config.identifier

    @property
    def name(self) -> str:
        """Return the device name."""
        return self.device_config.name

    @property
    def address(self) -> str | None:
        """Return the optional device address."""
        return self.device_config.address

    @property
    def state(self) -> str:
        """Return the device state."""
        return "ON" if self.is_connected else "OFF"

    @property
    def attributes(self) -> dict[str, any]:
        """Return the device attributes."""
        return {
            MediaAttr.STATE: self.state,
        }

    @property
    def lights(self) -> list[LutronLightInfo]:
        """Return the list of light entities."""
        return self._lights

    @property
    def covers(self) -> list[LutronCoverInfo]:
        """Return the list of cover entities."""
        return self._covers

    @property
    def scenes(self) -> list[LutronSceneInfo]:
        """Return the list of scene entities."""
        return self._scenes

    @property
    def scene(self) -> str | None:
        """Return the current scene."""
        return self._scene.name if self._scene else None

    # ─────────────────────────────────────────────────────────────────
    # ExternalClientDevice abstract methods implementation
    # ─────────────────────────────────────────────────────────────────

    async def create_client(self) -> Smartbridge:
        """Create the Smartbridge client instance."""
        return Smartbridge.create_tls(
            self._device_config.address,
            self._key_path,
            self._cert_path,
            self._bridge_cert_path,
        )

    async def connect_client(self) -> None:
        """Connect the Smartbridge client."""
        self._lutron_smart_hub = self._client
        await self._lutron_smart_hub.connect()
        _LOG.info("[%s] Connected to Lutron device", self.log_id)

        # Update lights and scenes after connection
        self._update_lights()
        for light in self._lights:
            self._lutron_smart_hub.add_subscriber(light.device_id, self._update_lights)
        self._update_scenes()

    async def disconnect_client(self) -> None:
        """Disconnect the Smartbridge client."""
        if self._lutron_smart_hub:
            await self._lutron_smart_hub.close()
            self._lutron_smart_hub = None

    def check_client_connected(self) -> bool:
        """Check if the Smartbridge client is connected."""
        return self._lutron_smart_hub is not None and self._lutron_smart_hub.logged_in

    def _update_lights(self) -> None:
        if not self._lutron_smart_hub:
            return
        update = {}
        try:
            self._lights = self.get_lights()

            for entity in self._lights:
                update = {}
                update[LightAttr.STATE] = "ON" if entity.current_state > 0 else "OFF"
                update[LightAttr.BRIGHTNESS] = int(entity.current_state * 255 / 100)

                self.events.emit(
                    DeviceEvents.UPDATE,
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
        if not self._lutron_smart_hub:
            return
        update = {}
        update[MediaAttr.STATE] = self.state

        try:
            self._scenes = self.get_scenes()
            update[MediaAttr.SOURCE_LIST] = [scene.name for scene in self._scenes]

            self.events.emit(
                DeviceEvents.UPDATE,
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
        if not self._lutron_smart_hub:
            return []
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
        if not self._lutron_smart_hub:
            return []
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
        if not self._lutron_smart_hub:
            _LOG.error("[%s] Not connected", self.log_id)
            return
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
                DeviceEvents.UPDATE,
                create_entity_id(
                    self.device_config.identifier,
                    "0",
                    EntityTypes.MEDIA_PLAYER,
                ),
                {MediaAttr.SOURCE: scene.name},
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error(
                "[%s] Error activating scene %s: %s", self.log_id, scene.name, err
            )

    async def turn_on_light(self, light_id: str, brightness: int = None) -> None:
        """Turn on a light with a specific brightness."""
        if not self._lutron_smart_hub:
            _LOG.error("[%s] Not connected", self.log_id)
            return
        try:
            if brightness is not None:
                await self._lutron_smart_hub.set_value(light_id, brightness)
            else:
                await self._lutron_smart_hub.turn_on(light_id)
                self.events.emit(
                    DeviceEvents.UPDATE,
                    create_entity_id(
                        self.device_config.identifier,
                        light_id,
                        EntityTypes.LIGHT,
                    ),
                    {LightAttr.STATE: "ON", LightAttr.BRIGHTNESS: brightness},
                )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Error turning on light %s: %s", self.log_id, light_id, err)

    async def turn_off_light(self, light_id: str) -> None:
        """Turn off a light."""
        if not self._lutron_smart_hub:
            _LOG.error("[%s] Not connected", self.log_id)
            return
        try:
            await self._lutron_smart_hub.turn_off(light_id)
            self.events.emit(
                DeviceEvents.UPDATE,
                create_entity_id(
                    self.device_config.identifier,
                    light_id,
                    EntityTypes.LIGHT,
                ),
                {LightAttr.STATE: "OFF", LightAttr.BRIGHTNESS: 0},
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error(
                "[%s] Error turning off light %s: %s", self.log_id, light_id, err
            )

    async def toggle_light(self, light_id: str) -> None:
        """Toggle a light."""
        if not self._lutron_smart_hub:
            _LOG.error("[%s] Not connected", self.log_id)
            return
        try:
            is_on = self._lutron_smart_hub.is_on(light_id)
            if is_on:
                await self._lutron_smart_hub.turn_off(light_id)
            else:
                await self._lutron_smart_hub.turn_on(light_id)
            self.events.emit(
                DeviceEvents.UPDATE,
                create_entity_id(
                    self.device_config.identifier,
                    light_id,
                    EntityTypes.LIGHT,
                ),
                {
                    LightAttr.STATE: "ON" if not is_on else "OFF",
                    LightAttr.BRIGHTNESS: 100 if not is_on else 0,
                },
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Error toggling light %s: %s", self.log_id, light_id, err)
