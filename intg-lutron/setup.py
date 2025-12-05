#!/usr/bin/env python3

"""Module that includes all functions needed for the setup and reconfiguration process"""

import logging
import os
import sys
from ipaddress import ip_address
from typing import Any

from const import LutronConfig
from pylutron_caseta.pairing import async_pair
from pylutron_caseta.smartbridge import Smartbridge
from ucapi import RequestUserInput, SetupError
from ucapi_framework import BaseSetupFlow

_LOG = logging.getLogger(__name__)

_MANUAL_INPUT_SCHEMA = RequestUserInput(
    {"en": "Lutron Caseta Setup"},
    [
        {
            "id": "info",
            "label": {
                "en": "Setup your Lutron Caseta Device",
            },
            "field": {
                "label": {
                    "value": {
                        "en": (
                            "Please supply the IP address of your Lutron Caseta Device."
                        ),
                    }
                }
            },
        },
        {
            "field": {"text": {"value": ""}},
            "id": "address",
            "label": {
                "en": "IP Address",
            },
        },
        {
            "id": "setup_info",
            "label": {
                "en": "",
            },
            "field": {
                "label": {
                    "value": {
                        "en": "After pressing 'Next', press the small black button on the back of your Lutron Caseta Smart Hub to complete the pairing process.",
                    }
                }
            },
        },
    ],
)


class LutronSetupFlow(BaseSetupFlow[LutronConfig]):
    """
    Setup flow for Lutron integration.

    Handles Lutron device configuration through SSDP discovery or manual entry.
    """

    def get_manual_entry_form(self) -> RequestUserInput:
        """
        Return the manual entry form for device setup.

        :return: RequestUserInput with form fields for manual configuration
        """
        return _MANUAL_INPUT_SCHEMA

    def get_additional_discovery_fields(self) -> list[dict]:
        """
        Return additional fields for discovery-based setup.

        :return: List of dictionaries defining additional fields
        """
        return [
            {
                "id": "info",
                "label": {
                    "en": "",
                },
                "field": {
                    "label": {
                        "value": {
                            "en": "After pressing 'Next', press the small black button on the back of your Lutron Caseta Smart Hub to complete the pairing process.",
                        }
                    }
                },
            },
        ]

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> LutronConfig | SetupError | RequestUserInput:
        """
        Handle the artwork selection response and complete setup.

        This is called after user selects artwork preferences.
        """

        address = input_values["address"]
        data = await async_pair(address)
        with open(f"{get_path()}/caseta-bridge.crt", "w") as cacert:
            cacert.write(data["ca"])
        with open(f"{get_path()}/caseta.crt", "w") as cert:
            cert.write(data["cert"])
        with open(f"{get_path()}/caseta.key", "w") as key:
            key.write(data["key"])

        if address != "":
            # Check if input is a valid ipv4 or ipv6 address
            try:
                ip_address(address)
            except ValueError:
                _LOG.error("The entered ip address %s is not valid", address)
                return _MANUAL_INPUT_SCHEMA

            _LOG.info("Entered ip address: %s", address)

            try:
                lutron_smart_hub: Smartbridge = Smartbridge.create_tls(
                    address,
                    f"{get_path()}/caseta.key",
                    f"{get_path()}/caseta.crt",
                    f"{get_path()}/caseta-bridge.crt",
                )
                try:
                    await lutron_smart_hub.connect()
                    devices = lutron_smart_hub.get_devices()
                finally:
                    await lutron_smart_hub.close()

                smarthub = devices["1"]

                return LutronConfig(
                    identifier=smarthub["serial"],
                    address=address,
                    name=smarthub["name"].replace("_", " "),
                    model=smarthub["model"],
                )

            except Exception as ex:  # pylint: disable=broad-exception-caught
                _LOG.error("Unable to connect at IP: %s. Exception: %s", address, ex)
                _LOG.info(
                    "Please check if you entered the correct ip of the lutron hub"
                )
                return _MANUAL_INPUT_SCHEMA
        else:
            _LOG.info("No ip address entered")
            return _MANUAL_INPUT_SCHEMA


def get_path() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.environ["UC_DATA_HOME"]
    return "./data"
