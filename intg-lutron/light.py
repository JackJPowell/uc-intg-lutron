"""
Media-player entity functions.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
import re
from typing import Any

import ucapi
from bridge import LutronLightInfo, SmartHub
from const import LutronDevice
from ucapi import EntityTypes, light
from ucapi.light import Attributes, Light, States
from ucapi_framework import create_entity_id

_LOG = logging.getLogger(__name__)


class LutronLight(Light):
    """Representation of a Lutron Light entity."""

    def __init__(
        self,
        config_device: LutronDevice,
        light_info: LutronLightInfo,
        device: SmartHub | None = None,
    ):
        """Initialize the class."""
        _LOG.debug("Lutron Light init")
        entity_id = create_entity_id(
            entity_type=EntityTypes.LIGHT,
            device_id=config_device.identifier,
            entity_id=light_info.device_id,
        )
        self.config = config_device
        self.device = device
        self.identifier = light_info.device_id
        self.features = [
            light.Features.ON_OFF,
            light.Features.TOGGLE,
            light.Features.DIM,
        ]

        if re.search(r"claro", light_info.type, re.IGNORECASE):
            self.features.pop(self.features.index(light.Features.DIM), None)

        state = States.OFF
        super().__init__(
            entity_id,
            light_info.name.replace("_", " "),
            self.features,
            attributes={
                Attributes.STATE: state,
                Attributes.BRIGHTNESS: 0,
            },
            cmd_handler=self.cmd_handler,
        )

    # pylint: disable=too-many-statements
    async def cmd_handler(
        self, entity: Light, cmd_id: str, params: dict[str, Any] | None
    ) -> ucapi.StatusCodes:
        """
        Lutron light entity command handler.

        Called by the integration-API if a command is sent to a configured Lutron light entity.

        :param entity: Lutron light entity
        :param cmd_id: command
        :param params: optional command parameters
        :return: status code of the command. StatusCodes.OK if the command succeeded.
        """
        _LOG.info(
            "Got %s command request: %s %s", entity.id, cmd_id, params if params else ""
        )

        try:
            match cmd_id:
                case light.Commands.ON:
                    if Attributes.BRIGHTNESS in params:
                        brightness = int(params[Attributes.BRIGHTNESS])
                        brightness = int(brightness * 100 / 255)
                        if brightness < 0 or brightness > 100:
                            _LOG.error(
                                "Invalid brightness value %s for command %s",
                                brightness,
                                cmd_id,
                            )
                            return ucapi.StatusCodes.BAD_REQUEST

                    res = await self.device.turn_on_light(
                        f"{self.identifier}", brightness=brightness
                    )
                case light.Commands.OFF:
                    _LOG.debug("Sending OFF command to Light")
                    res = await self.device.turn_off_light(f"{self.identifier}")
                case light.Commands.TOGGLE:
                    _LOG.debug("Sending TOGGLE command to Light")
                    res = await self.device.toggle_light(f"{self.identifier}")

        except Exception as ex:  # pylint: disable=broad-except
            _LOG.error("Error executing command %s: %s", cmd_id, ex)
            return ucapi.StatusCodes.BAD_REQUEST
        _LOG.debug("Command %s executed successfully: %s", cmd_id, res)
        return ucapi.StatusCodes.OK
