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
        return RequestUserInput(
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

        # Store certificates in variables to be saved in config
        ca_cert = data["ca"]
        cert = data["cert"]
        key = data["key"]

        if address != "":
            # Check if input is a valid ipv4 or ipv6 address
            try:
                ip_address(address)
            except ValueError:
                _LOG.error("The entered ip address %s is not valid", address)
                return self.get_manual_entry_form()

            _LOG.info("Entered ip address: %s", address)

            try:
                # Get data path - write access on remote is limited to data directory
                data_path = get_path()

                # Create data directory if it doesn't exist
                os.makedirs(data_path, exist_ok=True)

                # Write certificates to files in data directory for connection test
                key_path = os.path.join(data_path, "caseta.key")
                cert_path = os.path.join(data_path, "caseta.crt")
                ca_cert_path = os.path.join(data_path, "caseta-bridge.crt")

                with open(key_path, "w", encoding="utf-8") as key_file:
                    key_file.write(key)

                with open(cert_path, "w", encoding="utf-8") as cert_file:
                    cert_file.write(cert)

                with open(ca_cert_path, "w", encoding="utf-8") as ca_cert_file:
                    ca_cert_file.write(ca_cert)

                lutron_smart_hub: Smartbridge = Smartbridge.create_tls(
                    address,
                    key_path,
                    cert_path,
                    ca_cert_path,
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
                    ca_cert=ca_cert,
                    cert=cert,
                    key=key,
                )

            except Exception as ex:  # pylint: disable=broad-exception-caught
                _LOG.error("Unable to connect at IP: %s. Exception: %s", address, ex)
                _LOG.info(
                    "Please check if you entered the correct ip of the lutron hub"
                )
                return self.get_manual_entry_form()
        else:
            _LOG.info("No ip address entered")
            return self.get_manual_entry_form()


def get_path() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.environ["UC_DATA_HOME"]
    return "./data"
