"""
Button entity functions.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from typing import Any

import ucapi
from bridge import SmartHub
from const import LutronDevice, LutronSceneInfo
from ucapi import Button, EntityTypes, button
from ucapi_framework import create_entity_id

_LOG = logging.getLogger(__name__)


class LutronButton(Button):
    """Representation of a Lutron Button entity."""

    def __init__(
        self,
        config: LutronDevice,
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
        self, entity: Button, cmd_id: str, params: dict[str, Any] | None
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
        try:
            match cmd_id:
                case button.Commands.PUSH:
                    await self.device.activate_scene(scene_id=self.scene_id)

        except Exception as ex:  # pylint: disable=broad-except
            _LOG.error("Error executing command %s: %s", cmd_id, ex)
            return ucapi.StatusCodes.BAD_REQUEST
        return ucapi.StatusCodes.OK
