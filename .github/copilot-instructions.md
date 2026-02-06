# Copilot Instructions for yt_dlp_hass

## Project Overview
Home Assistant custom integration wrapping the `yt-dlp` Python library. Enables video downloads from YouTube and 1000+ sites via Home Assistant services. Distributed via HACS, pairs with [`yt_dlp-card`](https://github.com/ybk5053/yt_dlp-card) for UI.

## Architecture

### Integration Type: Service-Only, Single Config Entry
- **No YAML config**: All setup via UI (Configuration → Integrations)
- **Single instance**: `single_config_entry: true` in [manifest.json](custom_components/yt_dlp/manifest.json) - only one allowed
- **Service-based**: `integration_type: "service"` - exposes `yt_dlp.download` service, no entities except state tracker

### Core Data Flow
1. User calls `yt_dlp.download` service with URL + options → 
2. [__init__.py](custom_components/yt_dlp/__init__.py) `download()` validates URL, merges options → 
3. Runs `YoutubeDL` in executor thread → 
4. `progress_hook()` updates `yt_dlp.downloader` state attributes → 
5. Frontend card (optional) reads state for live progress

### State Entity Pattern
```python
hass.states.async_set(f"{DOMAIN}.downloader", len(attr), attr)
```
- **Entity ID**: `yt_dlp.downloader` (created in `async_setup_entry`)
- **State value**: Integer count of active downloads
- **Attributes**: Dict keyed by filename → `{speed, downloaded, total, eta}`
- **Why**: Home Assistant lacks native progress tracking for long-running services; state attributes provide real-time updates without creating dynamic entities

## Critical Implementation Patterns

### Thread Safety: Executor + Event Loop
**Problem**: `yt-dlp` is blocking; Home Assistant is async. Progress hooks run in executor thread but must update Home Assistant state.

**Solution** in [__init__.py](custom_components/yt_dlp/__init__.py):
```python
# Run blocking download in executor
await hass.async_add_executor_job(_download)

# Update state from executor thread via event loop
def progress_hook(d):
    hass.loop.call_soon_threadsafe(
        hass.states.async_set, f"{DOMAIN}.downloader", len(attr), attr
    )
```
**Rule**: ALWAYS use `async_add_executor_job()` for blocking I/O. ALWAYS use `call_soon_threadsafe()` when background threads touch Home Assistant.

### Service Schema: URL Validation + Options Passthrough
```python
schema=vol.Schema({
    vol.Required("url"): lambda v: v if urlparse(v).scheme else 
        ((_ for _ in ()).throw(ValueError(vol.error.UrlInvalid("expected a URL"))))
}, extra=vol.ALLOW_EXTRA)
```
- **`extra=vol.ALLOW_EXTRA`**: Allows arbitrary yt-dlp options (format, subtitles, etc.) without predefining schema
- **URL validator**: Inline lambda checks `urlparse().scheme` - throws voluptuous error if missing
- **Why not predefined schema**: yt-dlp has 100+ options; passthrough gives full flexibility

### Options Forwarding to yt-dlp
```python
for k, v in call.data.items():
    if k not in ["url", "progress_hooks", "paths"]:
        ydl_opts[k] = v
```
Blacklist approach: block reserved keys, forward everything else. Users reference [YoutubeDL.py](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py) for options.

### Config Flow: Directory Creation with Error Handling
```python
if not await self.hass.async_add_executor_job(os.path.isdir, download_path):
    await self.hass.async_add_executor_job(os.makedirs, download_path, 0o755)
```
- Runs in executor (file I/O is blocking)
- Creates with `0o755` permissions
- Catches `OSError` → shows `"cannot_create_folder"` error in UI (defined in [strings.json](custom_components/yt_dlp/strings.json))

## File Structure & Key Files

```
custom_components/yt_dlp/
├── __init__.py          # Core: setup, service registration, download logic
├── config_flow.py       # UI config: download path setup/reconfiguration
├── const.py             # Single constant: DOMAIN = "yt_dlp"
├── manifest.json        # HA metadata: dependencies (yt-dlp>=2024.12.6, quickjs>=1.19.2)
├── services.yaml        # Service UI metadata for Developer Tools
├── strings.json         # Base translations (config flow)
└── translations/
    └── en.json          # English localization (mirrors strings.json)
```

**[manifest.json](custom_components/yt_dlp/manifest.json)**: 
- `requirements`: `yt-dlp>=2024.12.6` (core), `quickjs>=1.19.2` (for YouTube's JS obfuscation)
- `integration_type: "service"` + `single_config_entry: true` = unique architecture

**[services.yaml](custom_components/yt_dlp/services.yaml)**: 
- Defines UI for `yt_dlp.download` in Developer Tools → Services
- Only documents `url` field; additional options are undocumented (intentional - users read yt-dlp docs)


### Local Testing (No Test Suite)
1. **Install**: `cp -r custom_components/yt_dlp <HA_CONFIG>/custom_components/`
2. **Restart Home Assistant**
3. **Add Integration**: Configuration → Integrations → "+ Add Integration" → "Youtube DLP"
4. **Test Service**: Developer Tools → Services → `yt_dlp.download` with `url: "https://www.youtube.com/watch?v=..."`
5. **Monitor State**: Developer Tools → States → Filter "yt_dlp.downloader" to see progress attributes

### Debugging Downloads
- **Logs**: Check Home Assistant logs for `_LOGGER.info()` / `_LOGGER.error()` from [__init__.py](custom_components/yt_dlp/__init__.py)
- **Progress tracking**: `progress_hook()` logs "Download finished" / "Download error" for each file
- **Common issues**: 
  - Missing QuickJS → `pip install quickjs>=1.19.2` (for YouTube's player client)
  - Permission errors → check download path in config entry

### yt-dlp Options Examples
Pass as service data fields (extra options allowed):
```yaml
service: yt_dlp.download
data:
  url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  format: "bestvideo[height<=1080]+bestaudio/best"  # Max 1080p
  outtmpl: "%(title)s.%(ext)s"                       # Custom filename
  writesubtitles: true                               # Download subtitles
  subtitleslangs: ["en"]                             # English subs only
```
Full options: [YoutubeDL.py](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L183-L632)

## Error Handling Patterns

### Common yt-dlp Exceptions
Current implementation catches all exceptions generically. For production-grade error handling, catch these specific yt-dlp errors:

```python
from yt_dlp.utils import (
    DownloadError,          # Generic download failure
    ExtractorError,         # Site extraction failed
    UnsupportedError,       # Site not supported
    GeoRestrictedError,     # Geographic restriction
    VideoUnavailable,       # Video deleted/private
    MaxDownloadsReached     # Hit download limit
)

def _download():
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except GeoRestrictedError as e:
        _LOGGER.error("Video geo-restricted: %s", url)
        raise HomeAssistantError("Video not available in your region")
    except VideoUnavailable as e:
        _LOGGER.error("Video unavailable: %s - %s", url, e)
        raise HomeAssistantError("Video is private, deleted, or unavailable")
    except ExtractorError as e:
        _LOGGER.error("Failed to extract video info: %s - %s", url, e)
        raise HomeAssistantError("Could not extract video information")
    except UnsupportedError:
        _LOGGER.error("Unsupported site: %s", url)
        raise HomeAssistantError("Site not supported by yt-dlp")
    except DownloadError as e:
        _LOGGER.error("Download failed: %s - %s", url, e)
        raise HomeAssistantError(f"Download failed: {e}")
```

**Network Errors**: yt-dlp handles retries internally via `"retries"` option (default: 10). For network-specific handling:
```python
import urllib.error
import socket

try:
    ydl.download([url])
except urllib.error.URLError as e:
    _LOGGER.error("Network error: %s", e.reason)
    raise HomeAssistantError("Network connection failed")
except socket.timeout:
    _LOGGER.error("Download timeout: %s", url)
    raise HomeAssistantError("Download timed out")
```

## Testing Strategy

### Creating a Test Suite
No test suite currently exists. Recommended structure using `pytest` and Home Assistant test utilities:

**Setup** (`tests/conftest.py`):
```python
import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yt_dlp.const import DOMAIN

@pytest.fixture
async def config_entry():
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={"file_path": "/tmp/yt_dlp_test"},
        unique_id=f"{DOMAIN}.downloader",
    )
```

**Integration Tests** (`tests/test_init.py`):
```python
import pytest
from homeassistant.core import HomeAssistant
from custom_components.yt_dlp import async_setup_entry, async_unload_entry

async def test_setup_unload(hass: HomeAssistant, config_entry):
    """Test integration setup and unload."""
    assert await async_setup_entry(hass, config_entry)
    assert hass.states.get("yt_dlp.downloader") is not None
    
    assert await async_unload_entry(hass, config_entry)
    assert hass.states.get("yt_dlp.downloader") is None

async def test_service_registration(hass: HomeAssistant, config_entry):
    """Test yt_dlp.download service is registered."""
    await async_setup_entry(hass, config_entry)
    assert hass.services.has_service("yt_dlp", "download")
```

**Service Tests** (`tests/test_services.py`):
```python
import pytest
from unittest.mock import patch, MagicMock

async def test_download_service_valid_url(hass: HomeAssistant, config_entry):
    """Test download service with valid URL."""
    await async_setup_entry(hass, config_entry)
    
    with patch("yt_dlp.YoutubeDL") as mock_ydl:
        await hass.services.async_call(
            "yt_dlp",
            "download",
            {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            blocking=True,
        )
        mock_ydl.return_value.__enter__.return_value.download.assert_called_once()

async def test_download_service_invalid_url(hass: HomeAssistant, config_entry):
    """Test download service rejects invalid URL."""
    await async_setup_entry(hass, config_entry)
    
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            "yt_dlp",
            "download",
            {"url": "not-a-url"},
            blocking=True,
        )
```

**Config Flow Tests** (`tests/test_config_flow.py`):
```python
from homeassistant import config_entries
from custom_components.yt_dlp.const import DOMAIN

async def test_form_user(hass: HomeAssistant):
    """Test user config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"file_path": "/tmp/test"},
    )
    assert result["type"] == "create_entry"
    assert result["data"] == {"file_path": "/tmp/test"}
```

**Running Tests**:
```bash
pip install pytest pytest-homeassistant-custom-component pytest-asyncio
pytest tests/ -v
```

## Coding Conventions

- **Domain references**: Use `DOMAIN` from [const.py](custom_components/yt_dlp/const.py), never hardcode `"yt_dlp"`
- **Logging**: Use `_LOGGER` (instantiated in `__init__.py`), not `print()` or `logging` directly
- **Async file operations**: ALWAYS wrap with `hass.async_add_executor_job()` (see `os.path.isdir`, `os.makedirs`)
- **State updates from threads**: ALWAYS use `hass.loop.call_soon_threadsafe()` (see `progress_hook()`)
- **Config entry access**: Read `config.data[CONF_FILE_PATH]` - config flow stores path, not options
- **Error messages**: Add to [strings.json](custom_components/yt_dlp/strings.json) `error` section + mirror to [translations/en.json](custom_components/yt_dlp/translations/en.json)
- **Legacy code**: `ansi_escape` regex at top of [__init__.py](custom_components/yt_dlp/__init__.py) is unused legacy code - safe to remove

## HACS Distribution

**[hacs.json](hacs.json)**: Minimal config - only requires `name` and `render_readme`
```json
{
  "name": "Youtube DLP",
  "render_readme": true
}
```
**Installation**: Users add `https://github.com/ybk5053/yt_dlp_hass` as custom repository (Integration category) in HACS.

## Integration Points

### With Home Assistant Core
- **Config Entries API**: `async_setup_entry()` / `async_unload_entry()` lifecycle
- **State Management**: `hass.states.async_set()` / `hass.states.get()` for progress tracking
- **Service Registration**: `hass.services.async_register()` with voluptuous schema
- **Executor Pool**: `hass.async_add_executor_job()` for blocking operations

### With External Libraries
- **yt-dlp**: `YoutubeDL` class with `progress_hooks` and `extractor_args`
  - **YouTube extraction config**: `["web", "android", "ios"]` tries multiple client APIs for reliability
    - **NOTE**: Android client has known issues and may fail; if downloads fail, override with `"extractor_args": {"youtube": {"player_client": ["web", "ios"]}}`
  - Skips HLS/DASH by default: `"skip": ["hls", "dash"]` (faster, more reliable downloads)
- **QuickJS**: Required for YouTube's JavaScript player obfuscation (automatic via yt-dlp)
- **voluptuous**: Schema validation with `vol.Required()`, `vol.ALLOW_EXTRA`
- **urllib.parse**: URL validation via `urlparse().scheme`

### With Frontend (Optional)
- **[yt_dlp-card](https://github.com/ybk5053/yt_dlp-card)**: Custom Lovelace card reads `yt_dlp.downloader` state
- **Developer Tools**: Built-in Home Assistant UI for calling services and viewing state

## When to Modify Key Files

- **Add/change service**: Edit [__init__.py](custom_components/yt_dlp/__init__.py) `async_setup_entry()`, update [services.yaml](custom_components/yt_dlp/services.yaml)
- **Change config fields**: Edit [config_flow.py](config_flow.py) schema + add translations to [strings.json](custom_components/yt_dlp/strings.json)
- **Update dependencies**: Modify `requirements` in [manifest.json](custom_components/yt_dlp/manifest.json)
- **Add translated language**: Create `translations/<lang>.json` mirroring [strings.json](custom_components/yt_dlp/strings.json) structure
