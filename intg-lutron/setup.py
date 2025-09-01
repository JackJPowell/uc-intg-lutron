#!/usr/bin/env python3

"""Module that includes all functions needed for the setup and reconfiguration process"""

import asyncio
import logging
from enum import IntEnum
from ipaddress import ip_address

import config
from config import LutronConfig
from discover import ZeroconfDiscovery
from pylutron_caseta.smartbridge import Smartbridge
from bridge import SmartHub
from ucapi import (
    AbortDriverSetup,
    DriverSetupRequest,
    IntegrationSetupError,
    RequestUserInput,
    SetupAction,
    SetupComplete,
    SetupDriver,
    SetupError,
    UserDataResponse,
)

_LOG = logging.getLogger(__name__)


class SetupSteps(IntEnum):
    """Enumeration of setup steps to keep track of user data responses."""

    INIT = 0
    CONFIGURATION_MODE = 1
    DISCOVER = 2
    DEVICE_CHOICE = 3


_setup_step = SetupSteps.INIT
_cfg_add_device: bool = False

_user_input_manual = RequestUserInput(
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
                            "Please supply the IP address or Hostname of your Lutron Caseta Device."
                        ),
                    }
                }
            },
        },
        {
            "field": {"text": {"value": ""}},
            "id": "ip",
            "label": {
                "en": "IP Address",
            },
        },
    ],
)


async def driver_setup_handler(
    msg: SetupDriver,
) -> SetupAction:
    """
    Dispatch driver setup requests to corresponding handlers.

    Either start the setup process or handle the provided user input data.

    :param msg: the setup driver request object, either DriverSetupRequest,
                UserDataResponse or UserConfirmationResponse
    :return: the setup action on how to continue
    """
    global _setup_step  # pylint: disable=global-statement
    global _cfg_add_device  # pylint: disable=global-statement

    if isinstance(msg, DriverSetupRequest):
        _setup_step = SetupSteps.INIT
        _cfg_add_device = False
        return await _handle_driver_setup(msg)
    if isinstance(msg, UserDataResponse):
        _LOG.debug("%s", msg)
        if (
            _setup_step == SetupSteps.CONFIGURATION_MODE
            and "action" in msg.input_values
        ):
            return await _handle_configuration_mode(msg)
        if (
            _setup_step == SetupSteps.DISCOVER
            and "ip" in msg.input_values
            and msg.input_values.get("ip") != "manual"
        ):
            return await _handle_creation(msg)
        if (
            _setup_step == SetupSteps.DISCOVER
            and "ip" in msg.input_values
            and msg.input_values.get("ip") == "manual"
        ):
            return await _handle_manual()
        _LOG.error("No user input was received for step: %s", msg)
    elif isinstance(msg, AbortDriverSetup):
        _LOG.info("Setup was aborted with code: %s", msg.error)
        _setup_step = SetupSteps.INIT

    return SetupError()


async def _handle_configuration_mode(
    msg: UserDataResponse,
) -> RequestUserInput | SetupComplete | SetupError:
    """
    Process user data response from the configuration mode screen.

    User input data:

    - ``choice`` contains identifier of selected device
    - ``action`` contains the selected action identifier

    :param msg: user input data from the configuration mode screen.
    :return: the setup action on how to continue
    """
    global _setup_step  # pylint: disable=global-statement
    global _cfg_add_device  # pylint: disable=global-statement

    action = msg.input_values["action"]

    # workaround for web-configurator not picking up first response
    await asyncio.sleep(1)

    match action:
        case "add":
            _cfg_add_device = True
            _setup_step = SetupSteps.DISCOVER
            return await _handle_discovery()
        case "update":
            choice = msg.input_values["choice"]
            if not config.devices.remove(choice):
                _LOG.warning("Could not update device from configuration: %s", choice)
                return SetupError(error_type=IntegrationSetupError.OTHER)
            _setup_step = SetupSteps.DISCOVER
            return await _handle_discovery()
        case "remove":
            choice = msg.input_values["choice"]
            if not config.devices.remove(choice):
                _LOG.warning("Could not remove device from configuration: %s", choice)
                return SetupError(error_type=IntegrationSetupError.OTHER)
            config.devices.store()
            return SetupComplete()
        case "reset":
            config.devices.clear()  # triggers device instance removal
            _setup_step = SetupSteps.DISCOVER
            return await _handle_discovery()
        case _:
            _LOG.error("Invalid configuration action: %s", action)
            return SetupError(error_type=IntegrationSetupError.OTHER)

    _setup_step = SetupSteps.DISCOVER
    return _user_input_manual


async def _handle_manual() -> RequestUserInput | SetupError:
    return _user_input_manual


async def _handle_discovery() -> RequestUserInput | SetupError:
    """
    Process user data response from the first setup process screen.
    """
    global _setup_step  # pylint: disable=global-statement

    zeroconf = ZeroconfDiscovery()
    await zeroconf.start()
    if len(zeroconf.discovered) > 0:
        _LOG.debug("Found Lutron Caseta Devices")

        dropdown_devices = []
        for device in zeroconf.discovered:
            dropdown_devices.append(
                {"id": device.address, "label": {"en": f"{device.type}"}}
            )

        dropdown_devices.append({"id": "manual", "label": {"en": "Setup Manually"}})

        return RequestUserInput(
            {"en": "Discovered Lutron Caseta Devices"},
            [
                {
                    "field": {
                        "dropdown": {
                            "value": dropdown_devices[0]["id"],
                            "items": dropdown_devices,
                        }
                    },
                    "id": "ip",
                    "label": {
                        "en": "Discovered Projectors:",
                    },
                },
                {
                    "field": {"text": {"value": ""}},
                    "id": "name",
                    "label": {
                        "en": "Projector Name",
                    },
                },
                {
                    "field": {"text": {"value": ""}},
                    "id": "password",
                    "label": {
                        "en": "Password (Optional)",
                    },
                },
            ],
        )

    # Initial setup, make sure we have a clean configuration
    config.devices.clear()  # triggers device instance removal
    _setup_step = SetupSteps.DISCOVER
    return _user_input_manual


async def _handle_driver_setup(
    msg: DriverSetupRequest,
) -> RequestUserInput | SetupError:
    """
    Start driver setup.

    Initiated by Remote Two to set up the driver. The reconfigure flag determines the setup flow:

    - Reconfigure is True:
        show the configured devices and ask user what action to perform (add, delete, reset).
    - Reconfigure is False: clear the existing configuration and show device discovery screen.
      Ask user to enter ip-address for manual configuration, otherwise auto-discovery is used.

    :param msg: driver setup request data, only `reconfigure` flag is of interest.
    :return: the setup action on how to continue
    """
    global _setup_step  # pylint: disable=global-statement

    reconfigure = msg.reconfigure
    _LOG.debug("Starting driver setup, reconfigure=%s", reconfigure)

    if reconfigure:
        _setup_step = SetupSteps.CONFIGURATION_MODE

        # get all configured devices for the user to choose from
        dropdown_devices = []
        for device in config.devices.all():
            dropdown_devices.append(
                {"id": device.identifier, "label": {"en": f"{device.name}"}}
            )

        dropdown_actions = [
            {
                "id": "add",
                "label": {
                    "en": "Add a new JVC Projector",
                },
            },
        ]

        # add remove & reset actions if there's at least one configured device
        if dropdown_devices:
            dropdown_actions.append(
                {
                    "id": "update",
                    "label": {
                        "en": "Update information for selected JVC Projector",
                    },
                },
            )
            dropdown_actions.append(
                {
                    "id": "remove",
                    "label": {
                        "en": "Remove selected JVC Projector",
                    },
                },
            )
            dropdown_actions.append(
                {
                    "id": "reset",
                    "label": {
                        "en": "Reset configuration and reconfigure",
                        "de": "Konfiguration zurücksetzen und neu konfigurieren",
                        "fr": "Réinitialiser la configuration et reconfigurer",
                    },
                },
            )
        else:
            # dummy entry if no devices are available
            dropdown_devices.append({"id": "", "label": {"en": "---"}})

        return RequestUserInput(
            {"en": "Configuration mode", "de": "Konfigurations-Modus"},
            [
                {
                    "field": {
                        "dropdown": {
                            "value": dropdown_devices[0]["id"],
                            "items": dropdown_devices,
                        }
                    },
                    "id": "choice",
                    "label": {
                        "en": "Configured Devices",
                        "de": "Konfigurerte Geräte",
                        "fr": "Appareils configurés",
                    },
                },
                {
                    "field": {
                        "dropdown": {
                            "value": dropdown_actions[0]["id"],
                            "items": dropdown_actions,
                        }
                    },
                    "id": "action",
                    "label": {
                        "en": "Action",
                        "de": "Aktion",
                        "fr": "Appareils configurés",
                    },
                },
            ],
        )

    # Initial setup, make sure we have a clean configuration
    config.devices.clear()  # triggers device instance removal
    _setup_step = SetupSteps.DISCOVER
    return await _handle_discovery()


async def _handle_creation(
    msg: DriverSetupRequest,
) -> RequestUserInput | SetupError:
    """
    Start driver setup.

    Initiated by Remote Two to set up the driver.

    :param msg: value(s) of input fields in the first setup screen.
    :return: the setup action on how to continue
    """

    ip = msg.input_values["ip"]
    password = msg.input_values["password"]
    name = msg.input_values["name"]

    if ip != "":
        # Check if input is a valid ipv4 or ipv6 address
        try:
            ip_address(ip)
        except ValueError:
            _LOG.error("The entered ip address %s is not valid", ip)
            return SetupError(IntegrationSetupError.NOT_FOUND)

        _LOG.info("Entered ip address: %s", ip)

        try:
            lutron_smart_hub: Smartbridge = Smartbridge.create_tls(
                ip, "caseta.key", "caseta.crt", "caseta-bridge.crt"
            )
            try:
                await lutron_smart_hub.connect()
                info = await lutron_smart_hub.get_devices()
            finally:
                await lutron_smart_hub.close()
            _LOG.debug("Lutron Smart Hub info: %s", info)

            device = LutronConfig(
                identifier="HOLD",
                address=ip,
            )

            config.devices.add_or_update(device)
        except Exception as ex:  # pylint: disable=broad-exception-caught
            _LOG.error("Unable to connect at IP: %s. Exception: %s", ip, ex)
            _LOG.info("Please check if you entered the correct ip of the projector")
            return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
    else:
        _LOG.info("No ip address entered")
        return SetupError(IntegrationSetupError.OTHER)
    _LOG.info("Setup complete")
    return SetupComplete()
