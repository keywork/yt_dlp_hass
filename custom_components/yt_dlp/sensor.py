"""Sensor platform for yt_dlp integration."""
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up yt_dlp sensor."""
    sensor = YTDLPDownloaderSensor(config_entry)
    async_add_entities([sensor], True)
    
    # Store sensor reference for progress updates
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    if "entities" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["entities"] = []
    hass.data[DOMAIN]["entities"].append(sensor)


class YTDLPDownloaderSensor(SensorEntity):
    """Sensor to track yt_dlp downloads."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self._config_entry = config_entry
        self._attr_name = "Downloader"
        self._attr_unique_id = f"{DOMAIN}_downloader"
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {}

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": "Youtube-DLP",
            "manufacturer": "yt-dlp",
            "model": "Video Downloader",
        }

    def update_progress(self, attributes: dict) -> None:
        """Update the sensor state and attributes."""
        self._attr_native_value = len(attributes)
        self._attr_extra_state_attributes = attributes
        self.async_write_ha_state()
