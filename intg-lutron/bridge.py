"""
This module implements the Lutron communication of the Remote Two/3 integration driver.

"""

import logging
from asyncio import AbstractEventLoop
from typing import Any
import os
import sys
from const import LutronCoverInfo, LutronConfig, LutronLightInfo, LutronSceneInfo
from pylutron_caseta.smartbridge import Smartbridge
from ucapi import EntityTypes, button, light, cover
from ucapi_framework import (
    ExternalClientDevice,
    create_entity_id,
    LightAttributes,
    ButtonAttributes,
    CoverAttributes,
    BaseIntegrationDriver,
)

_LOG = logging.getLogger(__name__)


class SmartHub(ExternalClientDevice):
    """Representing a Lutron Smart Hub Device."""

    def __init__(
        self,
        device_config: LutronConfig,
        loop: AbstractEventLoop | None = None,
        config_manager=None,
        driver: BaseIntegrationDriver | None = None,
    ) -> None:
        """Create instance."""
        super().__init__(
            device_config,
            loop=loop,
            watchdog_interval=30,
            reconnect_delay=5,
            max_reconnect_attempts=0,  # Infinite retries
            config_manager=config_manager,
            driver=driver,
        )

        self._lutron_smart_hub: Smartbridge | None = None
        self._lights: list[LutronLightInfo] = []
        self._covers: list[LutronCoverInfo] = []
        self._scenes: list[LutronSceneInfo] = []
        self._scene: LutronSceneInfo | None = None

        # Store entity attributes indexed by entity_id
        self._light_attributes: dict[str, LightAttributes] = {}
        self._button_attributes: dict[str, ButtonAttributes] = {}
        self._cover_attributes: dict[str, CoverAttributes] = {}

    @property
    def device_config(self) -> LutronConfig:
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
    def attributes(self) -> dict[str, Any]:
        """Return the device attributes."""
        return {
            "STATE": self.state,
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

    async def create_client(self) -> Smartbridge:
        """Create the Smartbridge client instance."""
        # Ensure certificate files exist and get their paths
        key_path, cert_path, ca_cert_path = self._ensure_certificate_files()

        return Smartbridge.create_tls(
            self._device_config.address,
            key_path,
            cert_path,
            ca_cert_path,
        )

    async def connect_client(self) -> None:
        """Connect the Smartbridge client."""
        # Ensure certificate files exist before connecting
        self._ensure_certificate_files()

        self._lutron_smart_hub = self._client
        await self._lutron_smart_hub.connect()
        _LOG.info("[%s] Connected to Lutron device", self.log_id)

        # Populate lights, covers, and scenes after connection
        self._lights = self.get_lights()
        self._covers = self.get_covers()
        self._scenes = self.get_scenes()

        # Initialize attributes for each light entity
        for light_info in self._lights:
            entity_id = create_entity_id(
                EntityTypes.LIGHT,
                self.device_config.identifier,
                light_info.device_id,
            )
            self._light_attributes[entity_id] = LightAttributes(
                STATE=light.States.ON
                if light_info.current_state > 0
                else light.States.OFF,
                BRIGHTNESS=int(light_info.current_state * 255 / 100),
            )
            # Subscribe to light updates
            self._lutron_smart_hub.add_subscriber(
                light_info.device_id, self._update_lights
            )

        # Initialize attributes for each cover entity
        for cover_info in self._covers:
            entity_id = create_entity_id(
                EntityTypes.COVER,
                self.device_config.identifier,
                cover_info.device_id,
            )
            state = (
                cover.States.OPEN
                if cover_info.current_state >= 5
                else cover.States.CLOSED
            )
            self._cover_attributes[entity_id] = CoverAttributes(
                STATE=state,
                POSITION=cover_info.current_state,
            )

        # Initialize attributes for each scene/button entity
        for scene_info in self._scenes:
            entity_id = create_entity_id(
                EntityTypes.BUTTON,
                self.device_config.identifier,
                scene_info.scene_id,
            )
            self._button_attributes[entity_id] = ButtonAttributes(
                STATE=button.States.AVAILABLE,
            )

    async def disconnect_client(self) -> None:
        """Disconnect the Smartbridge client."""
        if self._lutron_smart_hub:
            await self._lutron_smart_hub.close()
            self._lutron_smart_hub = None

    def check_client_connected(self) -> bool:
        """Check if the Smartbridge client is connected."""
        return self._lutron_smart_hub is not None and self._lutron_smart_hub.logged_in

    def get_device_attributes(
        self, entity_id: str
    ) -> LightAttributes | ButtonAttributes | CoverAttributes:
        """Get entity attributes by entity_id."""
        if entity_id in self._light_attributes:
            return self._light_attributes[entity_id]
        if entity_id in self._button_attributes:
            return self._button_attributes[entity_id]
        if entity_id in self._cover_attributes:
            return self._cover_attributes[entity_id]
        return LightAttributes()  # Default fallback

    def _update_lights(self) -> None:
        """Update light attributes from Lutron hub."""
        if not self._lutron_smart_hub:
            return
        try:
            self._lights = self.get_lights()

            for entity in self._lights:
                entity_id = create_entity_id(
                    EntityTypes.LIGHT,
                    self.device_config.identifier,
                    entity.device_id,
                )
                # Get old attributes to compare
                old_attributes = self._light_attributes.get(entity_id)

                # Update stored attributes
                new_attributes = LightAttributes(
                    STATE=light.States.ON
                    if entity.current_state > 0
                    else light.States.OFF,
                    BRIGHTNESS=int(entity.current_state * 255 / 100),
                )
                self._light_attributes[entity_id] = new_attributes

                # Emit update event if attributes changed
                if old_attributes != new_attributes:
                    # Get the entity from driver and call update
                    if self.driver:
                        light_entity = self.driver.get_entity_by_id(entity_id)
                        if light_entity:
                            light_entity.update(new_attributes)

        except Exception:  # pylint: disable=broad-exception-caught
            _LOG.exception("[%s] Light update error", self.log_id)

    def get_lights(self) -> list[Any]:
        """Return the list of light entities."""
        if not self._lutron_smart_hub:
            return []
        lights = self._lutron_smart_hub.get_devices_by_domain("light")
        switches = self._lutron_smart_hub.get_devices_by_domain("switch")
        light_list = []
        for entity in lights:
            light_list.append(
                LutronLightInfo(
                    device_id=entity.get("device_id", ""),
                    current_state=entity.get("current_state", 0),
                    type=entity.get("type", ""),
                    name=entity.get("name", ""),
                    model=entity.get("model", ""),
                )
            )
        # Merge switches into light list
        for entity in switches:
            light_list.append(
                LutronLightInfo(
                    device_id=entity.get("device_id", ""),
                    current_state=entity.get("current_state", 0),
                    type=entity.get("type", ""),
                    name=entity.get("name", ""),
                    model=entity.get("model", ""),
                )
            )
        return light_list

    def get_covers(self) -> list[Any]:
        """Return the list of cover entities."""
        if not self._lutron_smart_hub:
            return []
        covers = self._lutron_smart_hub.get_devices_by_domain("cover")
        cover_list = []
        for entity in covers:
            cover_list.append(
                LutronCoverInfo(
                    device_id=entity.get("device_id", ""),
                    current_state=entity.get("current_state", 0),
                    type=entity.get("type", ""),
                    name=entity.get("name", ""),
                    model=entity.get("model", ""),
                )
            )
        return cover_list

    def get_scenes(self) -> list[Any]:
        """Return the list of scene entities."""
        if not self._lutron_smart_hub:
            return []
        scenes = self._lutron_smart_hub.get_scenes()
        scene_list = []
        for scene in scenes.values():
            scene_list.append(
                LutronSceneInfo(
                    scene_id=scene.get("scene_id", ""),
                    name=scene.get("name", ""),
                )
            )
        return scene_list

    async def activate_scene(self, scene_id: str) -> None:
        """Activate a scene."""
        if not self._lutron_smart_hub:
            _LOG.error("[%s] Not connected", self.log_id)
            return
        scene: LutronSceneInfo | None = next(
            (s for s in self.scenes if s.scene_id == scene_id), None
        )
        if scene is None:
            _LOG.error("[%s] Scene %s not found", self.log_id, scene_id)
            return
        try:
            await self._lutron_smart_hub.activate_scene(scene.scene_id)
            self._scene = scene
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error(
                "[%s] Error activating scene %s: %s", self.log_id, scene.name, err
            )

    async def turn_on_light(self, light_id: str, brightness: int | None = None) -> None:
        """Turn on a light with a specific brightness."""
        if not self._lutron_smart_hub:
            _LOG.error("[%s] Not connected", self.log_id)
            return
        try:
            if brightness is not None:
                await self._lutron_smart_hub.set_value(light_id, brightness)
            else:
                await self._lutron_smart_hub.turn_on(light_id)

            # Update stored attributes
            entity_id = create_entity_id(
                EntityTypes.LIGHT,
                self.device_config.identifier,
                light_id,
            )
            # Convert Lutron brightness (0-100) back to ucapi (0-255)
            ucapi_brightness = (
                int(brightness * 255 / 100) if brightness is not None else 255
            )
            self._light_attributes[entity_id] = LightAttributes(
                STATE=light.States.ON,
                BRIGHTNESS=ucapi_brightness,
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

            # Update stored attributes
            entity_id = create_entity_id(
                EntityTypes.LIGHT,
                self.device_config.identifier,
                light_id,
            )
            self._light_attributes[entity_id] = LightAttributes(
                STATE=light.States.OFF,
                BRIGHTNESS=0,
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error(
                "[%s] Error turning off light %s: %s", self.log_id, light_id, err
            )

    async def open_cover(self, cover_id: str) -> None:
        """Open a cover."""
        if not self._lutron_smart_hub:
            _LOG.error("[%s] Not connected", self.log_id)
            return
        try:
            await self._lutron_smart_hub.set_value(cover_id, 100)

            # Update stored attributes
            entity_id = create_entity_id(
                EntityTypes.COVER,
                self.device_config.identifier,
                cover_id,
            )
            self._cover_attributes[entity_id] = CoverAttributes(
                STATE=cover.States.OPEN,
                POSITION=100,
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Error opening cover %s: %s", self.log_id, cover_id, err)

    async def close_cover(self, cover_id: str) -> None:
        """Close a cover."""
        if not self._lutron_smart_hub:
            _LOG.error("[%s] Not connected", self.log_id)
            return
        try:
            await self._lutron_smart_hub.set_value(cover_id, 0)

            # Update stored attributes
            entity_id = create_entity_id(
                EntityTypes.COVER,
                self.device_config.identifier,
                cover_id,
            )
            self._cover_attributes[entity_id] = CoverAttributes(
                STATE=cover.States.CLOSED,
                POSITION=0,
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Error closing cover %s: %s", self.log_id, cover_id, err)

    async def stop_cover(self, cover_id: str) -> None:
        """Stop a cover."""
        if not self._lutron_smart_hub:
            _LOG.error("[%s] Not connected", self.log_id)
            return
        try:
            await self._lutron_smart_hub.stop_cover(cover_id)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Error stopping cover %s: %s", self.log_id, cover_id, err)

    async def set_cover_position(self, cover_id: str, position: int) -> None:
        """Set cover position (0-100)."""
        if not self._lutron_smart_hub:
            _LOG.error("[%s] Not connected", self.log_id)
            return
        try:
            await self._lutron_smart_hub.set_value(cover_id, position)

            # Update stored attributes
            entity_id = create_entity_id(
                EntityTypes.COVER,
                self.device_config.identifier,
                cover_id,
            )
            state = cover.States.OPEN if position >= 5 else cover.States.CLOSED
            self._cover_attributes[entity_id] = CoverAttributes(
                STATE=state,
                POSITION=position,
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error(
                "[%s] Error setting cover %s position: %s", self.log_id, cover_id, err
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

            # Update stored attributes
            entity_id = create_entity_id(
                EntityTypes.LIGHT,
                self.device_config.identifier,
                light_id,
            )
            self._light_attributes[entity_id] = LightAttributes(
                STATE=light.States.ON if not is_on else light.States.OFF,
                BRIGHTNESS=255 if not is_on else 0,
            )
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Error toggling light %s: %s", self.log_id, light_id, err)

    def _ensure_certificate_files(self) -> tuple[str, str, str]:
        """
        Ensure certificate files exist in the data directory.

        Writes certificates from config to files if they don't exist or if force_write is True.
        Returns the paths to the certificate files.

        :return: Tuple of (key_path, cert_path, ca_cert_path)
        """
        # Determine data path - write access on remote is limited to data directory
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            data_path = os.environ["UC_DATA_HOME"]
        else:
            data_path = "./data"

        # Create data directory if it doesn't exist
        os.makedirs(data_path, exist_ok=True)

        # Certificate file paths
        key_path = os.path.join(data_path, "caseta.key")
        cert_path = os.path.join(data_path, "caseta.crt")
        ca_cert_path = os.path.join(data_path, "caseta-bridge.crt")

        # Check if any certificate files are missing
        if (
            not os.path.exists(key_path)
            or not os.path.exists(cert_path)
            or not os.path.exists(ca_cert_path)
        ):
            _LOG.debug(
                "[%s] Certificate files missing, creating from config", self.log_id
            )

            with open(key_path, "w", encoding="utf-8") as key_file:
                key_file.write(self._device_config.key)

            with open(cert_path, "w", encoding="utf-8") as cert_file:
                cert_file.write(self._device_config.cert)

            with open(ca_cert_path, "w", encoding="utf-8") as ca_cert_file:
                ca_cert_file.write(self._device_config.ca_cert)

        return key_path, cert_path, ca_cert_path
