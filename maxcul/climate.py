"""
Support for MAX! thermostats using the maxcul component.

For more details about this platform, please refer to the documentation
https://home-assistant.io/components/climate.maxcul/
"""
import asyncio
import logging
from typing import List

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.components.climate import ClimateEntity, PLATFORM_SCHEMA
from homeassistant.components.climate.const import (
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_OFF,
    HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_NONE,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.const import (
    TEMP_CELSIUS, ATTR_TEMPERATURE, CONF_ID, CONF_NAME,
    CONF_DEVICES, ATTR_BATTERY_LEVEL
)
import homeassistant.helpers.config_validation as cv

from . import (
    DATA_MAXCUL_CONNECTION, SIGNAL_THERMOSTAT_UPDATE
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TEMPERATURE = 12

SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE | SUPPORT_PRESET_MODE

DEVICE_SCHEMA = vol.Schema({
    vol.Required(CONF_ID): cv.positive_int,
    vol.Optional(CONF_NAME): cv.string
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICES): vol.Schema({
        cv.string: DEVICE_SCHEMA
    })
})

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Add a new MAX! thermostat."""
    if not CONF_DEVICES in config:
        return
    maxcul_connection = hass.data[DATA_MAXCUL_CONNECTION]
    devices = [
        MaxThermostat(
            maxcul_connection,
            device[CONF_ID],
            device.get(CONF_NAME, key)
        )
        for key, device
        in config[CONF_DEVICES].items()
    ]
    add_entities(devices)


class MaxThermostat(ClimateEntity):
    """A MAX! thermostat backed by a CUL stick."""

    def __init__(self, maxcul_connection, device_id: int, name: str):
        """Initialize a new device for the given thermostat id."""
        self._name: str = name
        self._device_id: int = device_id
        self._maxcul_connection = maxcul_connection
        self._current_temperature: float = None
        self._target_temperature: float = None
        self._mode: str = None
        self._battery_low: bool = False

        self._maxcul_connection.add_paired_device(self._device_id)

    @asyncio.coroutine
    def async_added_to_hass(self):
        """Connect to thermostat update signal."""
        from maxcul import (
            ATTR_DEVICE_ID, ATTR_DESIRED_TEMPERATURE,
            ATTR_MEASURED_TEMPERATURE, ATTR_MODE,
            ATTR_BATTERY_LOW
        )

        @callback
        def update(payload):
            """Handle thermostat update events."""
            device_id = payload.get(ATTR_DEVICE_ID)
            if device_id != self._device_id:
                return

            current_temperature = payload.get(ATTR_MEASURED_TEMPERATURE)
            target_temperature = payload.get(ATTR_DESIRED_TEMPERATURE)
            mode = payload.get(ATTR_MODE)
            battery_low = payload.get(ATTR_BATTERY_LOW)

            if current_temperature is not None:
                self._current_temperature = current_temperature
            if target_temperature is not None:
                self._target_temperature = target_temperature
            if mode is not None:
                self._mode = mode
            if battery_low is not None:
                self._battery_low = battery_low

            self.async_schedule_update_ha_state()

        async_dispatcher_connect(
            self.hass, SIGNAL_THERMOSTAT_UPDATE, update)

        self._maxcul_connection.wakeup(self._device_id)

    @property
    def supported_features(self) -> int:
        """Return the features supported by this device."""
        return SUPPORT_FLAGS

    @property
    def should_poll(self) -> bool:
        """Return whether this device must be polled."""
        return False

    @property
    def name(self) -> str:
        """Return the name of this device."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return a unique id for this device"""
        return self._device_id

    @property
    def device_state_attributes(self) -> dict:
        """Return device specific attributes."""
        return {
            ATTR_BATTERY_LEVEL:  5 if self._battery_low else 100
        }

    @property
    def max_temp(self) -> int:
        """Return the maximum temperature for this device."""
        from maxcul import MAX_TEMPERATURE
        return MAX_TEMPERATURE

    @property
    def min_temp(self) -> int:
        """Return the minimum temperature for this device."""
        from maxcul import MIN_TEMPERATURE
        return MIN_TEMPERATURE

    @property
    def temperature_unit(self) -> str:
        """Return the temperature unit of this device."""
        return TEMP_CELSIUS

    @property
    def current_temperature(self) -> float:
        """Return the currently measured temperature of this device."""
        return self._current_temperature

    @property
    def target_temperature(self) -> float:
        """Return the target temperature of this device."""
        return self._target_temperature

    def set_temperature(self, **kwargs):
        """Set the target temperature of this device."""
        from maxcul import MODE_MANUAL
        target_temperature = kwargs.get(ATTR_TEMPERATURE)
        if target_temperature is None:
            return

        self._maxcul_connection.set_temperature(
            self._device_id,
            target_temperature,
            self._mode or MODE_MANUAL)

    @property
    def hvac_mode(self):
        """Return the current HVAC mode of this device."""
        from maxcul import (
            MODE_AUTO, MODE_BOOST, MODE_MANUAL,
            MIN_TEMPERATURE
        )
        if self._mode in [ MODE_AUTO, MODE_BOOST ]:
            return HVAC_MODE_AUTO
        if (
            self._mode == MODE_MANUAL 
            and self._target_temperature == MIN_TEMPERATURE
        ):
            return HVAC_MODE_OFF
        return HVAC_MODE_HEAT

    @property
    def hvac_modes(self) -> List[str]:
        """All supported HVAC modes of this device."""
        return [HVAC_MODE_AUTO, HVAC_MODE_HEAT, HVAC_MODE_OFF]


    def set_hvac_mode(self, hvac_mode: str):
        """Set new HVAC mode"""
        from maxcul import (
            MODE_AUTO, MODE_MANUAL,
            MIN_TEMPERATURE
        )
        if hvac_mode == HVAC_MODE_OFF:
            self._maxcul_connection.set_temperature(
                self._device_id,
                MIN_TEMPERATURE,
                MODE_MANUAL
            )
        elif hvac_mode == HVAC_MODE_AUTO:
            self._maxcul_connection.set_temperature(
                self._device_id,
                self._target_temperature,
                MODE_AUTO
            )
        else:
            self._maxcul_connection.set_temperature(
                self._device_id,
                self._target_temperature,
                MODE_MANUAL
            )

    @property
    def preset_modes(sefl) -> str:
        return [
            PRESET_BOOST,
            PRESET_NONE
        ]

    @property
    def preset_mode(self) -> str:
        from maxcul import MODE_BOOST
        if self._mode == MODE_BOOST:
            return PRESET_BOOST
        return PRESET_NONE

    def set_preset_mode(self, preset_mode: str):
        from maxcul import MODE_BOOST
        if preset_mode == PRESET_BOOST:
            self._maxcul_connection.set_temperature(
                self._device_id,
                self._target_temperature,
                MODE_BOOST
            )