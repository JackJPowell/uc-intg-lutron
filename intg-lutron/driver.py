#!/usr/bin/env python3
"""
This module implements a Unfolded Circle integration driver for Lutron devices.

:copyright: (c) 2023-2024 by Unfolded Circle ApS.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
import os
import sys
from typing import Any

import config
import setup
import ucapi
import ucapi.api as uc
from ucapi import light
from light import LutronLight
from config import LutronConfig, device_from_entity_id
import bridge

_LOG = logging.getLogger("driver")  # avoid having __main__ in log messages
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)

# Global variables
api = uc.IntegrationAPI(_LOOP)
_configured_devices: dict[str, bridge.SmartHub] = {}


@api.listens_to(ucapi.Events.CONNECT)
async def on_r2_connect_cmd() -> None:
    """Connect all configured devices when the Remote Two/3 sends the connect command."""
    _LOG.debug("Client connect command: connecting device(s)")
    await api.set_device_state(
        ucapi.DeviceStates.CONNECTED
    )  # just to make sure the device state is set
    for device in _configured_devices.values():
        await device.connect()


@api.listens_to(ucapi.Events.DISCONNECT)
async def on_r2_disconnect_cmd():
    """Disconnect all configured devices when the Remote Two/3 sends the disconnect command."""
    _LOG.debug("Client disconnect command: disconnecting device(s)")
    for device in _configured_devices.values():
        await device.disconnect(continue_polling=False)


@api.listens_to(ucapi.Events.ENTER_STANDBY)
async def on_r2_enter_standby() -> None:
    """
    Enter standby notification from Remote Two/3.

    Disconnect every Lutron device instances.
    """
    _LOG.debug("Enter standby event: disconnecting device(s)")
    for device in _configured_devices.values():
        await device.disconnect(continue_polling=False)


@api.listens_to(ucapi.Events.EXIT_STANDBY)
async def on_r2_exit_standby() -> None:
    """
    Exit standby notification from Remote Two/3.

    Connect all Lutron device instances.
    """
    _LOG.debug("Exit standby event: connecting device(s)")
    for device in _configured_devices.values():
        await device.connect()


@api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)
async def on_subscribe_entities(entity_ids: list[str]) -> None:
    """
    Subscribe to given entities.

    :param entity_ids: entity identifiers.
    """
    _LOG.debug("Subscribe entities event: %s", entity_ids)

    for entity_id in entity_ids:
        device_id = device_from_entity_id(entity_id)
        if device_id is not None:
            # this is a device entity, so we need to check if it is already configured
            if device_id in _configured_devices:
                device = _configured_devices[device_id]
                _LOG.info("Add '%s' to configured devices and connect", device.name)
                _LOG.debug("Device State: %s", device.state)
                if device.state is None:
                    state = light.States.UNAVAILABLE
                else:
                    state = device.state
                api.configured_entities.update_attributes(
                    entity_id, {light.Attributes.STATE: state}
                )
                # await device.connect()
                continue

        device = config.devices.get(device_id)
        if device:
            _add_configured_device(device)
        else:
            _LOG.error(
                "Failed to subscribe entity %s: no Lutron device instance found",
                entity_id,
            )


@api.listens_to(ucapi.Events.UNSUBSCRIBE_ENTITIES)
async def on_unsubscribe_entities(entity_ids: list[str]) -> None:
    """On unsubscribe, we disconnect the objects and remove listeners for events."""
    _LOG.debug("Unsubscribe entities event: %s", entity_ids)
    for entity_id in entity_ids:
        device_id = device_from_entity_id(entity_id)
        if device_id is None:
            continue
        _configured_devices[device_id].events.remove_all_listeners()


async def on_device_connected(device_id: str):
    """Handle device connection."""
    _LOG.debug("Lutron device connected: %s", device_id)
    state = light.States.UNKNOWN
    if device_id not in _configured_devices:
        _LOG.warning("Lutron device %s is not configured", device_id)
        return

    for entity_id in _entities_from_device_id(device_id):
        configured_entity = api.configured_entities.get(entity_id)
        if configured_entity is None:
            _LOG.debug(
                "Device connected : entity %s is not configured, ignoring it", entity_id
            )
            continue

        device = _configured_devices[device_id]
        state = device.state

        if configured_entity.entity_type == ucapi.EntityTypes.LIGHT:
            api.configured_entities.update_attributes(
                entity_id,
                {ucapi.light.Attributes.STATE: state},
            )
        elif configured_entity.entity_type == ucapi.EntityTypes.COVER:
            api.configured_entities.update_attributes(
                entity_id, {ucapi.cover.Attributes.STATE: state}
            )
    await api.set_device_state(ucapi.DeviceStates.CONNECTED)


async def on_device_disconnected(device_id: str):
    """Handle device disconnection."""
    _LOG.debug("Lutron device disconnected: %s", device_id)

    for entity_id in _entities_from_device_id(device_id):
        configured_entity = api.configured_entities.get(entity_id)
        if configured_entity is None:
            continue

        if configured_entity.entity_type == ucapi.EntityTypes.LIGHT:
            api.configured_entities.update_attributes(
                entity_id,
                {ucapi.light.Attributes.STATE: ucapi.light.States.UNAVAILABLE},
            )
        elif configured_entity.entity_type == ucapi.EntityTypes.COVER:
            api.configured_entities.update_attributes(
                entity_id,
                {ucapi.cover.Attributes.STATE: ucapi.cover.States.UNAVAILABLE},
            )


async def on_device_connection_error(device_id: str, message):
    """Set entities of Lutron device to state UNAVAILABLE if device connection error occurred."""
    _LOG.error(message)

    for entity_id in _entities_from_device_id(device_id):
        configured_entity = api.configured_entities.get(entity_id)
        if configured_entity is None:
            continue

        if configured_entity.entity_type == ucapi.EntityTypes.LIGHT:
            api.configured_entities.update_attributes(
                entity_id,
                {ucapi.light.Attributes.STATE: ucapi.light.States.UNAVAILABLE},
            )
        elif configured_entity.entity_type == ucapi.EntityTypes.COVER:
            api.configured_entities.update_attributes(
                entity_id,
                {ucapi.cover.Attributes.STATE: ucapi.cover.States.UNAVAILABLE},
            )

    await api.set_device_state(ucapi.DeviceStates.ERROR)


# pylint: disable=too-many-branches,too-many-statements
async def on_device_update(entity_id: str, update: dict[str, Any] | None) -> None:
    """
    Update attributes of configured media-player entity if Device properties changed.

    :param entity_id: Device media-player entity identifier
    :param update: dictionary containing the updated properties or None
    """
    target_entity = None
    for identifier in _entities_from_device_id(entity_id):
        attributes = {}
        configured_entity = api.available_entities.get(identifier)
        if configured_entity is None:
            return

        if isinstance(configured_entity, LutronLight):
            target_entity = api.available_entities.get(identifier)
        # elif isinstance(configured_entity, LutronCover):
        #     target_entity = api.available_entities.get(identifier)

        if "state" in update:
            attributes[ucapi.light.Attributes.STATE] = update["state"]

        if attributes:
            if api.configured_entities.contains(identifier):
                api.configured_entities.update_attributes(identifier, attributes)
            else:
                api.available_entities.update_attributes(identifier, attributes)


def _add_configured_device(device_config: LutronConfig, connect: bool = False) -> None:
    # the device should not yet be configured, but better be safe
    if device_config.identifier in _configured_devices:
        _LOG.debug(
            "DISCONNECTING: Existing config device updated, update the running device %s",
            device_config,
        )
        device = _configured_devices[device_config.identifier]
    else:
        _LOG.debug(
            "Adding new device: %s (%s) %s",
            device_config.identifier,
            device_config.name,
            device_config.address,
        )
        device = bridge.SmartHub(device_config, loop=_LOOP)
        device.events.on(bridge.EVENTS.CONNECTED, on_device_connected)
        device.events.on(bridge.EVENTS.DISCONNECTED, on_device_disconnected)
        device.events.on(bridge.EVENTS.ERROR, on_device_connection_error)
        device.events.on(bridge.EVENTS.UPDATE, on_device_update)

        _configured_devices[device.identifier] = device

    async def start_connection():
        await device.connect()

    if connect:
        _LOOP.create_task(start_connection())

    _register_available_entities(device_config, device)


def _register_available_entities(
    device_config: LutronConfig, device: bridge.SmartHub
) -> bool:
    """
    Add a new device to the available entities.

    :param identifier: identifier
    :param name: Friendly name
    :return: True if added, False if the device was already in storage.
    """
    _LOG.info("_register_available_entities for %s", device_config.name)
    # get devices from bridge by domain and create entities
    entities = []
    for entity in entities:
        if api.available_entities.contains(entity.id):
            api.available_entities.remove(entity.id)
        api.available_entities.add(entity)
    return True


def _entities_from_device_id(device_id: str) -> list[str]:
    """
    Return all associated entity identifiers of the given device.

    :param device_id: the device identifier
    :return: list of entity identifiers
    """
    # store a list of entities from device and return
    return [f"media_player.{device_id}", f"remote.{device_id}"]


def on_device_added(device: LutronConfig) -> None:
    """Handle a newly added device in the configuration."""
    _LOG.debug("New device added: %s", device)
    _add_configured_device(device, connect=False)


def on_device_removed(device: LutronConfig | None) -> None:
    """Handle a removed device in the configuration."""
    if device is None:
        _LOG.debug(
            "Configuration cleared, disconnecting & removing all configured device instances"
        )
        for device in _configured_devices.values():
            # _LOOP.create_task(device.disconnect(continue_polling=False))
            device.events.remove_all_listeners()
        _configured_devices.clear()
        api.configured_entities.clear()
        api.available_entities.clear()
    else:
        if device.identifier in _configured_devices:
            _LOG.debug("Disconnecting from removed device %s", device.identifier)
            device = _configured_devices.pop(device.identifier)
            # _LOOP.create_task(device.disconnect(continue_polling=False))
            device.events.remove_all_listeners()
            entity_id = device.identifier
            api.configured_entities.remove(entity_id)
            api.available_entities.remove(entity_id)


async def main():
    """Start the Remote Two/3 integration driver."""
    logging.basicConfig()

    level = os.getenv("UC_LOG_LEVEL", "DEBUG").upper()
    logging.getLogger("bridge").setLevel(level)
    logging.getLogger("driver").setLevel(level)
    logging.getLogger("config").setLevel(level)
    logging.getLogger("discover").setLevel(level)
    logging.getLogger("setup").setLevel(level)

    # load paired devices
    config.devices = config.Devices(
        api.config_dir_path, on_device_added, on_device_removed
    )
    # best effort migration (if required): network might not be available during startup
    # await config.devices.migrate()

    for device_config in config.devices.all():
        _add_configured_device(device_config)

    await api.init("driver.json", setup.driver_setup_handler)


if __name__ == "__main__":
    _LOOP.run_until_complete(main())
    _LOOP.run_forever()
