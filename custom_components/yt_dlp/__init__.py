"""The hass_ytdlp component."""
import asyncio
import logging
import os
import re
import time

import voluptuous as vol

from homeassistant.const import CONF_FILE_PATH
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from yt_dlp import YoutubeDL

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

async def async_setup_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    """Set up the hass_ytdlp component."""    
    hass.states.async_set(f"{DOMAIN}.downloader", "0")
    
    # Create download directory asynchronously
    download_path = config.data[CONF_FILE_PATH]
    if not await hass.async_add_executor_job(os.path.isdir, download_path):
        await hass.async_add_executor_job(os.makedirs, download_path, 0o755)

    def progress_hook(d):
        """Update download progress & Update the state of the entity"""
        state = hass.states.get(f"{DOMAIN}.downloader")
        if state is None:
            _LOGGER.warning("Downloader state entity not found")
            return
            
        attr = dict(state.attributes)
        filename = d["info_dict"]["filename"].split("/")[-1]
        
        if d["status"] == "finished":
            attr.pop(filename, None)
            _LOGGER.info("Download finished: %s", filename)
        elif d["status"] == "downloading":
            attr[filename] = {
                "speed": d.get("speed", 0),
                "downloaded": d.get("downloaded_bytes", 0),
                "total": d.get("total_bytes", "Unknown"),
                "eta": d.get("eta", 0),
            }
        elif d["status"] == "error":
            attr.pop(filename, None)
            _LOGGER.error("Download error: %s", filename)
        
        # Schedule state update on the event loop
        hass.loop.call_soon_threadsafe(
            hass.states.async_set, f"{DOMAIN}.downloader", len(attr), attr
        )

    async def download(call: ServiceCall):
        """Download a video."""
        url = call.data["url"]
        _LOGGER.info("Starting download: %s", url)
        
        ydl_opts = {
            'ignoreerrors': True,
            "progress_hooks": [progress_hook],
            "paths": {
                "home": config.data[CONF_FILE_PATH],
                "temp": "temp",
            },
            # Use android/mweb clients that work without PO tokens or JavaScript
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "mweb"],  # No PO token or QuickJS needed
                }
            },
        }
        
        # Pass through additional yt-dlp options
        for k, v in call.data.items():
            if k not in ["url", "progress_hooks", "paths"]:
                ydl_opts[k] = v
        
        # Run blocking yt-dlp operation in executor
        def _download():
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except Exception as e:
                _LOGGER.error("Download failed for %s: %s", url, e)
                raise
        
        await hass.async_add_executor_job(_download)
        _LOGGER.info("Download completed: %s", url)

    from urllib.parse import urlparse
    hass.services.async_register( 
        DOMAIN,
        "download",
        download,
        schema=vol.Schema({vol.Required("url"): lambda v: v if urlparse(v).scheme else ((_ for _ in ()).throw(ValueError(vol.error.UrlInvalid("expected a URL"))))}, extra=vol.ALLOW_EXTRA),
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    hass.states.async_remove(f"{DOMAIN}.downloader")
    hass.services.async_remove(DOMAIN, "download")

    return True
