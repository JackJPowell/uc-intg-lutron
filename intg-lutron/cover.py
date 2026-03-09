"""
Cover entity functions.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from typing import Any

import ucapi
from bridge import SmartHub, LutronCoverInfo
from const import LutronConfig
from ucapi import EntityTypes, cover
from ucapi_framework import create_entity_id
from ucapi_framework.entities import CoverEntity

_LOG = logging.getLogger(__name__)


class LutronCover(CoverEntity):
    """Representation of a Lutron Cover entity."""

    def __init__(
        self,
        config: LutronConfig,
        cover_info: LutronCoverInfo,
        device: SmartHub | None = None,
    ):
        """Initialize the class."""
        _LOG.debug("Lutron Cover init")
        self.config = config
        self.device = device
        self._cover_id = cover_info.device_id

        super().__init__(
            create_entity_id(
                EntityTypes.COVER, config.identifier, cover_info.device_id
            ),
            cover_info.name,
            features=[
                cover.Features.OPEN,
                cover.Features.CLOSE,
                cover.Features.STOP,
                cover.Features.POSITION,
            ],
            attributes={
                cover.Attributes.STATE: cover.States.UNKNOWN,
                cover.Attributes.POSITION: 0,
            },
            device_class=cover.DeviceClasses.SHADE,
            cmd_handler=self.cover_cmd_handler,
        )

        if device:
            self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Sync entity state from device update."""
        if not self.device:
            return
        state = self.device.get_cover_state(self._cover_id)
        if state is None:
            return
        self.update(state)

    async def cover_cmd_handler(
        self,
        entity: CoverEntity,
        cmd_id: str,
        params: dict[str, Any] | None,
        _: Any | None = None,
    ) -> ucapi.StatusCodes:
        """
        Cover entity command handler.

        Called by the integration-API if a command is sent to a configured cover entity.

        :param entity: cover entity
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
                case cover.Commands.OPEN:
                    await self.device.open_cover(cover_id=self._cover_id)
                case cover.Commands.CLOSE:
                    await self.device.close_cover(cover_id=self._cover_id)
                case cover.Commands.STOP:
                    await self.device.stop_cover(cover_id=self._cover_id)
                case cover.Commands.POSITION:
                    if params and "position" in params:
                        position = params["position"]
                        await self.device.set_cover_position(
                            cover_id=self._cover_id, position=position
                        )

        except Exception as ex:  # pylint: disable=broad-except
            _LOG.error("Error executing command %s: %s", cmd_id, ex)
            return ucapi.StatusCodes.BAD_REQUEST
        return ucapi.StatusCodes.OK
