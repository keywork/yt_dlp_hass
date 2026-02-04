# Copilot Instructions for yt_dlp_hass

## Project Overview
This is a Home Assistant custom integration that wraps the `yt-dlp` Python library, allowing users to download videos from YouTube and other sites directly from Home Assistant. It's distributed via HACS (Home Assistant Community Store) and can be paired with the [`yt_dlp-card`](https://github.com/ybk5053/yt_dlp-card) frontend component.

## Architecture

### Component Structure
- **Single-entry integration**: Uses `single_config_entry: true` - only one instance allowed
- **Service integration**: Defined as `integration_type: "service"` - primarily exposes Home Assistant services
- **Config flow only**: No `configuration.yaml` support - all setup via UI

### Key Components

**[custom_components/yt_dlp/__init__.py](custom_components/yt_dlp/__init__.py)**: Core integration logic
- `async_setup_entry()`: Creates `yt_dlp.downloader` state entity and registers `yt_dlp.download` service
- `progress_hook()`: Real-time progress tracking via state attributes (speed, downloaded bytes, total, eta)
- `download()`: Service handler that wraps `YoutubeDL` with user-provided options

**[custom_components/yt_dlp/config_flow.py](custom_components/yt_dlp/config_flow.py)**: UI configuration
- Single required field: `CONF_FILE_PATH` (download directory)
- Auto-creates directory if missing (with `0o755` permissions)
- Supports reconfiguration via `async_step_reconfigure()`

**State Management Pattern**: 
```python
hass.states.set(f"{DOMAIN}.downloader", len(attr), attr)
```
- Entity ID: `yt_dlp.downloader`
- State value: count of active downloads
- Attributes: dict keyed by filename, containing progress data

## Critical Patterns

### Service Registration with URL Validation
The `download` service uses an inline lambda validator for URLs:
```python
schema=vol.Schema({
    vol.Required("url"): lambda v: v if urlparse(v).scheme else 
        ((_ for _ in ()).throw(ValueError(vol.error.UrlInvalid("expected a URL"))))
}, extra=vol.ALLOW_EXTRA)
```
This allows `extra=vol.ALLOW_EXTRA` so users can pass any yt-dlp option (format, subtitles, etc.) directly through service calls.

### yt-dlp Options Passthrough
All service call data except `url`, `progress_hooks`, and `paths` is forwarded to `YoutubeDL`:
```python
for k, v in call.data.items():
    if k not in ["url", "progress_hooks", "paths"]:
        ydl_opts[k] = v
```
Refer users to [`yt_dlp/YoutubeDL.py`](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py) for available options.

### Download Directory Structure
```python
"paths": {
    "home": config.data[CONF_FILE_PATH],  # User-configured base path
    "temp": "temp",                        # Relative temp subfolder
}
```

## Dependencies & Requirements
- **Runtime**: `yt-dlp` package (specified in [manifest.json](custom_components/yt_dlp/manifest.json))
- **Home Assistant**: Config entries API, state management, service registration
- **External validation**: Uses `voluptuous` for schema validation and `urllib.parse` for URL checking

## Testing & Development
No test suite present. For local testing:
1. Copy `custom_components/yt_dlp/` to Home Assistant's `custom_components/` directory
2. Restart Home Assistant
3. Add integration via UI: Configuration → Integrations → "Youtube DLP"
4. Test service via Developer Tools → Services → `yt_dlp.download`

## HACS Distribution
- **[hacs.json](hacs.json)**: Minimal metadata (`name`, `render_readme`)
- **Installation**: Users add repository URL as custom repository (Integration category)

## Translation & Localization
- **[strings.json](custom_components/yt_dlp/strings.json)**: Base translations (config flow labels, errors)
- **[translations/en.json](custom_components/yt_dlp/translations/en.json)**: English translations (mirrors strings.json)

## Conventions
- Domain constant: Use `DOMAIN` from [const.py](custom_components/yt_dlp/const.py), not hardcoded strings
- Logging: Use `_LOGGER` (defined in `__init__.py`) for all log output
- File paths: Always validate with `os.path.isdir()` and handle `OSError` during directory creation
- **Critical**: Always use `hass.async_add_executor_job()` for blocking I/O operations (file system, yt-dlp downloads)
- **Critical**: Use `hass.loop.call_soon_threadsafe()` when updating Home Assistant state from background threads

## Common yt-dlp Options
Users can pass these via service calls (see [YoutubeDL.py](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py) for full list):

**Format selection**:
```yaml
format: "bestvideo[height<=1080]+bestaudio/best[height<=1080]"  # Max 1080p
format: "bestaudio"  # Audio only
```

**Output template**:
```yaml
outtmpl: "%(title)s.%(ext)s"  # Custom filename
outtmpl: "%(uploader)s/%(playlist)s/%(playlist_index)s - %(title)s.%(ext)s"  # Organized structure
```

**Subtitles**:
```yaml
writesubtitles: true
writeautomaticsub: true
subtitleslangs: ["en", "es"]
```

**Post-processing**:
```yaml
postprocessors:
  - key: FFmpegExtractAudio
    preferredcodec: mp3
    preferredquality: "192"
```

## Home Assistant Integration Patterns

### State Entity Management
The integration creates a persistent state entity `yt_dlp.downloader`:
- **State value**: Integer count of active downloads
- **Attributes**: Dict with filename keys containing progress data
- Used by [`yt_dlp-card`](https://github.com/ybk5053/yt_dlp-card) for real-time UI updates

### Thread-Safe State Updates
Progress hooks run in yt-dlp's worker threads. Must use:
```python
hass.loop.call_soon_threadsafe(
    hass.states.async_set, entity_id, state, attributes
)
```
Never call `hass.states.async_set()` directly from threads - will cause event loop errors.

### Executor Pattern for Blocking Operations
All blocking operations must run in executor to avoid freezing Home Assistant:
```python
# File system operations
await hass.async_add_executor_job(os.path.isdir, path)
await hass.async_add_executor_job(os.makedirs, path, 0o755)

# yt-dlp downloads (CPU/network intensive)
def _download():
    with YoutubeDL(opts) as ydl:
        ydl.download([url])

await hass.async_add_executor_job(_download)
```

## Troubleshooting Common Issues

### Service Not Appearing in Developer Tools
**Symptom**: `yt_dlp.download` service missing after integration setup  
**Causes**:
1. Integration not loaded - check Configuration → Integrations for errors
2. Service registration failed - check Home Assistant logs for exceptions during `async_setup_entry()`
3. Schema validation errors - look for voluptuous exceptions

**Fix**: Check logs with `grep -i yt_dlp home-assistant.log` or Developer Tools → Logs

### Downloads Not Starting
**Symptom**: Service call succeeds but no download activity  
**Causes**:
1. Blocking executor not being used - service handler will block event loop
2. Download directory doesn't exist or lacks permissions
3. Network issues or invalid URL

**Debug**:
```python
_LOGGER.info("Starting download: %s", url)  # Should appear in logs
_LOGGER.info("Download completed: %s", url)  # Should appear after download
```

### State Not Updating
**Symptom**: `yt_dlp.downloader` entity exists but attributes don't change  
**Causes**:
1. Thread-safety violation - using `async_set()` from worker thread
2. Progress hook not being called - check yt-dlp options
3. State entity was removed (integration reloaded mid-download)

**Fix**: Verify using `hass.loop.call_soon_threadsafe()` in progress_hook

### Permission Errors on Directory Creation
**Symptom**: `OSError` during integration setup or reconfigure  
**Fix**: Ensure Home Assistant user has write permissions to parent directory, or pre-create directory with `mkdir -p /path && chown homeassistant:homeassistant /path`

### Integration Points with External Systems

**Frontend Card** ([`yt_dlp-card`](https://github.com/ybk5053/yt_dlp-card)):
- Reads `yt_dlp.downloader` state via WebSocket API
- Expects attributes in format: `{filename: {speed, downloaded, total, eta}}`
- Filename extracted as last path component: `d["info_dict"]["filename"].split("/")[-1]`

**Automation Integration**:
```yaml
service: yt_dlp.download
data:
  url: "{{ trigger.event.data.url }}"
  format: "bestaudio"
  outtmpl: "%(title)s.%(ext)s"
```

**File System Integration**:
- Downloads saved to user-configured `CONF_FILE_PATH`
- Temp files in `{CONF_FILE_PATH}/temp/` subdirectory
- Can be monitored by Home Assistant folder sensors or file triggers
