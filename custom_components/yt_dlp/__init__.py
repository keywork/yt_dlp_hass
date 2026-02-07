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

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, config: ConfigEntry) -> bool:
    """Set up the hass_ytdlp component."""    
    # Forward entry setup to sensor platform
    await hass.config_entries.async_forward_entry_setups(config, PLATFORMS)
    
    # Create download directory asynchronously
    download_path = config.data[CONF_FILE_PATH]
    if not await hass.async_add_executor_job(os.path.isdir, download_path):
        await hass.async_add_executor_job(os.makedirs, download_path, 0o755)

    def progress_hook(d):
        """Update download progress & Update the state of the entity"""
        # Get sensor entity from registry
        entity_id = f"sensor.{DOMAIN}_downloader"
        state = hass.states.get(entity_id)
        if state is None:
            _LOGGER.warning("Downloader sensor entity not found")
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
        
        # Update sensor entity (thread-safe)
        from .sensor import YTDLPDownloaderSensor
        for entity in hass.data.get(DOMAIN, {}).get("entities", []):
            if isinstance(entity, YTDLPDownloaderSensor):
                hass.loop.call_soon_threadsafe(entity.update_progress, attr)
                break

    async def download(call: ServiceCall):
        """Download a video."""
        url = call.data["url"]
        audio_only = call.data.get("audio_only", False)
        _LOGGER.info("Starting download: %s (audio_only: %s)", url, audio_only)
        
        ydl_opts = {
            'ignoreerrors': True,
            'noplaylist': True,  # Only download single video, not entire playlist
            "progress_hooks": [progress_hook],
            "paths": {
                "home": config.data[CONF_FILE_PATH],
                "temp": "temp",
            },
            # Clean filename without video ID
            "outtmpl": "%(title)s.%(ext)s",
            # Use android/mweb clients that work without PO tokens or JavaScript
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "mweb"],  # No PO token or QuickJS needed
                }
            },
            # Post-processor to clean up common title suffixes
            "postprocessors": [{
                "key": "ModifyMetadata",
                "title": [
                    # Remove common video type indicators
                    {"regex": r"\s*\(Official\s+(Video|Audio|Music\s+Video|Lyric\s+Video)\)\s*$", "replace": ""},
                    # Remove [Official Video] style brackets
                    {"regex": r"\s*\[Official\s+(Video|Audio|Music\s+Video|Lyric\s+Video)\]\s*$", "replace": ""},
                    # Remove trailing dashes/pipes with channel names
                    {"regex": r"\s*[-|]\s*[^-|]+$", "replace": ""},
                ],
            }],
        }
        
        # If audio_only is requested, add audio extraction postprocessor
        if audio_only:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'].append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            })
        
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
    hass.services.async_remove(DOMAIN, "download")
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    return unload_ok
