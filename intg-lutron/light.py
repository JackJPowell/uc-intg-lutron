"""
Media-player entity functions.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from typing import Any
import ucapi


from config import LutronConfig, create_entity_id
from ucapi import EntityTypes, light
from ucapi.light import Attributes, Light, States
from bridge import SmartHub, LutronLightInfo

_LOG = logging.getLogger(__name__)

features = [light.Features.ON_OFF, light.Features.TOGGLE, light.Features.DIM]


class LutronLight(Light):
    """Representation of a Lutron Light entity."""

    def __init__(
        self,
        config_device: LutronConfig,
        bridge: SmartHub,
        light_info: LutronLightInfo,
    ):
        """Initialize the class."""
        self._bridge = bridge
        self._light_info = light_info
        _LOG.debug("Lutron Light init")
        entity_id = create_entity_id(light_info.device_id, EntityTypes.LIGHT)
        self.config = config_device

        state = States.ON if light_info.current_state > 0 else States.OFF
        super().__init__(
            entity_id,
            config_device.name,
            features,
            attributes={
                Attributes.STATE: state,
                Attributes.BRIGHTNESS: light_info.current_state,
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
            await self._bridge._lutron_smart_hub.connect()
            identifier = entity.id.split(".", 1)[1]

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
                        _LOG.debug(
                            "Sending BRIGHTNESS command to Light: %s", brightness
                        )
                        res = await self._bridge._lutron_smart_hub.set_value(
                            f"{identifier}", brightness
                        )
                    else:
                        res = await self._bridge._lutron_smart_hub.turn_on(
                            f"{identifier}"
                        )
                case light.Commands.OFF:
                    _LOG.debug("Sending OFF command to Light")
                    res = await self._bridge._lutron_smart_hub.turn_off(f"{identifier}")
                case light.Commands.TOGGLE:
                    _LOG.debug("Sending TOGGLE command to Light")
                    return ucapi.StatusCodes.NOT_IMPLEMENTED
                    # res = await self._bridge._lutron_smart_hub.toggle(f"{identifier}")

        except Exception as ex:  # pylint: disable=broad-except
            _LOG.error("Error executing command %s: %s", cmd_id, ex)
            return ucapi.StatusCodes.BAD_REQUEST
        finally:
            await self._bridge._lutron_smart_hub.close()
        _LOG.debug("Command %s executed successfully: %s", cmd_id, res)
        return ucapi.StatusCodes.OK
