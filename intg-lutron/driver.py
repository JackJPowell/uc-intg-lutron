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
from const import LutronConfig
from discover import LutronDiscovery
from light import LutronLight
from setup import LutronSetupFlow
from ucapi_framework import BaseConfigManager, BaseIntegrationDriver, get_config_path

_LOG = logging.getLogger("driver")


async def main():
    """Start the Remote Two/3 integration driver."""
    logging.basicConfig()

    level = os.getenv("UC_LOG_LEVEL", "DEBUG").upper()
    logging.getLogger("bridge").setLevel(level)
    logging.getLogger("driver").setLevel(level)
    logging.getLogger("discover").setLevel(level)
    logging.getLogger("setup").setLevel(level)

    driver = BaseIntegrationDriver(
        device_class=SmartHub,
        entity_classes=[
            lambda cfg, dev: [
                LutronLight(cfg, light_info, dev)
                for light_info in dev.lights
            ],
            lambda cfg, dev: [
                LutronButton(cfg, scene_info, dev)
                for scene_info in dev.scenes
            ]
        ],
        require_connection_before_registry=True,
    )

    driver.config_manager = BaseConfigManager(
        get_config_path(driver.api.config_dir_path),
        driver.on_device_added,
        driver.on_device_removed,
        config_class=LutronConfig,
    )

    await driver.register_all_configured_devices()

    discovery = LutronDiscovery(service_type="_lutron._tcp.local.", timeout=2)
    setup_handler = LutronSetupFlow.create_handler(driver, discovery)
    await driver.api.init("driver.json", setup_handler)

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())

