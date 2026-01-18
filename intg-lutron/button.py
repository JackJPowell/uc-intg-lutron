"""
Button entity functions.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from typing import Any

import ucapi
from bridge import SmartHub
from const import LutronConfig, LutronSceneInfo
from ucapi import Button, EntityTypes, button
from ucapi_framework import create_entity_id, Entity

_LOG = logging.getLogger(__name__)


class LutronButton(Button, Entity):
    """Representation of a Lutron Button entity."""

    def __init__(
        self,
        config: LutronConfig,
        scene_info: LutronSceneInfo,
        device: SmartHub | None = None,
    ):
        entity_id = create_entity_id(
            EntityTypes.BUTTON,
            config.identifier,
            scene_info.scene_id,
        )
        self.config = config
        self.device = device
        self.scene_id = scene_info.scene_id

        super().__init__(
            entity_id,
            scene_info.name,
            cmd_handler=self.button_cmd_handler,
        )

    async def button_cmd_handler(
        self, entity: ucapi.Entity, cmd_id: str, params: dict[str, Any] | None, _: Any | None = None
    ) -> ucapi.StatusCodes:
        """
        Button entity command handler.

        Called by the integration-API if a command is sent to a configured button entity.

        :param entity: button entity
        :param cmd_id: command
        :param params: optional command parameters
        :return: status code of the command. StatusCodes.OK if the command succeeded.
        """
        _LOG.info(
            "Got %s command request: %s %s", entity.id, cmd_id, params if params else ""
        )
        
        if not self.device:
            _LOG.error("Device not available")
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE
        
        try:
            match cmd_id:
                case button.Commands.PUSH:
                    await self.device.activate_scene(scene_id=self.scene_id)
                    # Update entity attributes from device
                    self.update(self.device.get_device_attributes(entity.id))

        except Exception as ex:  # pylint: disable=broad-except
            _LOG.error("Error executing command %s: %s", cmd_id, ex)
            return ucapi.StatusCodes.BAD_REQUEST
        return ucapi.StatusCodes.OK
