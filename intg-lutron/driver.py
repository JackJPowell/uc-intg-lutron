#!/usr/bin/env python3
"""
This module implements a Unfolded Circle integration driver for Lutron devices.

:copyright: (c) 2023-2024 by Unfolded Circle ApS.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
import os

from bridge import SmartHub
from button import LutronButton
from const import LutronDevice
from discover import LutronDiscovery
from light import LutronLight
from setup import LutronSetupFlow
from ucapi import EntityTypes
from ucapi.button import Attributes as ButtonAttr
from ucapi.light import Attributes as LightAttr
from ucapi.light import States as LightStates
from ucapi_framework import BaseDeviceManager, BaseIntegrationDriver, get_config_path

_LOG = logging.getLogger("driver")


class LutronIntegrationDriver(BaseIntegrationDriver[SmartHub, LutronDevice]):
    async def refresh_entity_state(self, entity_id):
        """
        Refresh the state of a configured entity by querying the device.
        """
        device_id = self.device_from_entity_id(entity_id)
        device = self._configured_devices[device_id]
        match self.entity_type_from_entity_id(entity_id):
            case EntityTypes.BUTTON.value:
                entity = next(
                    (
                        scene
                        for scene in device.scenes
                        if scene.scene_id == self.entity_from_entity_id(entity_id)
                    ),
                    None,
                )

                if entity is not None:
                    update = {}
                    update[ButtonAttr.STATE] = "AVAILABLE"
                    self.api.configured_entities.update_attributes(entity_id, update)
            case EntityTypes.LIGHT.value:
                entity = next(
                    (
                        light
                        for light in device.lights
                        if light.device_id == self.entity_from_entity_id(entity_id)
                    ),
                    None,
                )

                if entity is not None:
                    update = {}
                    update[LightAttr.STATE] = (
                        LightStates.ON if entity.current_state > 0 else LightStates.OFF
                    )
                    update[LightAttr.BRIGHTNESS] = int(entity.current_state * 255 / 100)
                    self.api.configured_entities.update_attributes(entity_id, update)

    async def async_register_available_entities(
        self, device_config: LutronDevice, device: SmartHub
    ) -> bool:
        """
        Register entities by querying the Lutron hub for its devices.

        This is called after the hub is connected and retrieves the actual
        devices from the Lutron network rather than from stored config.

        :param device: The connected SmartHub instance
        :return: True if entities were registered successfully
        """
        _LOG.info(
            "Registering available entities from Lutron hub: %s",
            device.identifier,
        )

        try:
            # Get lights from the hub (this queries the Lutron network)
            if device.lights is None:
                await device.get_lights()
            _LOG.info("Found %d lights on Lutron network", len(device.lights))

            # Get scenes from the hub (this queries the Lutron network)
            if device.scenes is None:
                await device.get_scenes()
            _LOG.info("Found %d scenes on Lutron network", len(device.scenes))

            entities = []

            # Create light entities from what the hub reports
            for light in device.lights:
                _LOG.debug(
                    "Registering light: %s (id %s)",
                    light.name,
                    light.device_id,
                )
                # Determine light type based on available information
                light_entity = LutronLight(device.device_config, light, device)
                entities.append(light_entity)

            # Create scene/button entities from what the hub reports
            for scene in device.scenes:
                _LOG.debug(
                    "Registering scene: %s (id %s)",
                    scene.name,
                    scene.scene_id,
                )
                button_entity = LutronButton(device.device_config, scene, device)
                entities.append(button_entity)

            # Register all entities with the API
            for entity in entities:
                if self.api.available_entities.contains(entity.id):
                    _LOG.debug("Removing existing entity: %s", entity.id)
                    self.api.available_entities.remove(entity.id)
                _LOG.debug("Adding entity: %s", entity.id)
                self.api.available_entities.add(entity)

            _LOG.info(
                "Successfully registered %d entities from Lutron hub",
                len(entities),
            )
            return True

        except Exception as ex:  # pylint: disable=broad-exception-caught
            _LOG.error("Error registering entities from hub: %s", ex)
            return False


async def main():
    """Start the Remote Two/3 integration driver."""
    logging.basicConfig()

    level = os.getenv("UC_LOG_LEVEL", "DEBUG").upper()
    logging.getLogger("bridge").setLevel(level)
    logging.getLogger("driver").setLevel(level)
    logging.getLogger("discover").setLevel(level)
    logging.getLogger("setup").setLevel(level)

    loop = asyncio.get_running_loop()

    driver = LutronIntegrationDriver(
        loop=loop,
        device_class=SmartHub,
        entity_classes=[LutronLight, LutronButton],
        require_connection_before_registry=True,
    )

    driver.config = BaseDeviceManager(
        get_config_path(driver.api.config_dir_path),
        driver.on_device_added,
        driver.on_device_removed,
        device_class=LutronDevice,
    )

    for device_config in list(driver.config.all()):
        await driver.async_add_configured_device(device_config)

    discovery = LutronDiscovery(service_type="_lutron._tcp.local.", timeout=2)

    setup_handler = LutronSetupFlow.create_handler(driver.config, discovery)

    await driver.api.init("driver.json", setup_handler)

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
