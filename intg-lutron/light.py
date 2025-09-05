"""
Media-player entity functions.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import re
import logging
from typing import Any
import ucapi
from config import LutronConfig, create_entity_id
from ucapi import EntityTypes, light
from ucapi.light import Attributes, Light, States
from bridge import LutronLightInfo
import bridge

_LOG = logging.getLogger(__name__)
_configured_devices: dict[str, bridge.SmartHub] = {}


class LutronLight(Light):
    """Representation of a Lutron Light entity."""

    def __init__(
        self,
        config_device: LutronConfig,
        light_info: LutronLightInfo,
        get_device: Any = None,
    ):
        """Initialize the class."""
        _LOG.debug("Lutron Light init")
        entity_id = create_entity_id(
            device_id=config_device.identifier,
            entity_id=light_info.device_id,
            entity_type=EntityTypes.LIGHT,
        )
        self.config = config_device
        self.get_device = get_device
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
            light_info.name,
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
        device = self.get_device(self.config.identifier)

        try:
            identifier = entity.id.split(".", 2)[2]
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

                    res = await device.turn_on_light(
                        f"{identifier}", brightness=brightness
                    )
                case light.Commands.OFF:
                    _LOG.debug("Sending OFF command to Light")
                    res = await device.turn_off_light(f"{identifier}")
                case light.Commands.TOGGLE:
                    _LOG.debug("Sending TOGGLE command to Light")
                    res = await device.toggle_light(f"{identifier}")

        except Exception as ex:  # pylint: disable=broad-except
            _LOG.error("Error executing command %s: %s", cmd_id, ex)
            return ucapi.StatusCodes.BAD_REQUEST
        _LOG.debug("Command %s executed successfully: %s", cmd_id, res)
        return ucapi.StatusCodes.OK
