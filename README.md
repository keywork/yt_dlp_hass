# Integration to use YT-DLP within Home Assistant

Integration can be used with [`yt_dlp-card`](https://github.com/keywork/yt_dlp-card) to see download status

**No QuickJS required** - Uses android/mweb clients for reliable downloads on Home Assistant OS

## Installation

### HACS

- Add Custom Repositories

```text
Repository: https://github.com/keywork/yt_dlp_hass
Category: Integration
```

### Manually

Clone or download this repository and copy the "yt_dlp" directory to your "custom_components" directory in your config directory

```<config directory>/custom_components/yt_dlp/...```

## Configuration

### Configuration via the "Configuration -> Integrations" section of the Home Assistant UI

- Search for the integration labeled "Youtube DLP" and select it.  
- Enter the path for the download directory.

## Downloading

### Default Behavior
- **Single video only**: By default, only downloads the specific video from a URL, even if it's part of a playlist
- To download an entire playlist, pass `noplaylist: false` in service data

### Via Developer tools -> Services

- Search for service "yt_dlp.download"
- Enter link to video download and click "call service"
- Additional options can be passed into the data in Yaml Mode

**Example - Download single video:**
```yaml
service: yt_dlp.download
data:
  url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
  # Will only download the specific video, not the entire playlist
```

**Example - Download entire playlist:**
```yaml
service: yt_dlp.download
data:
  url: "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
  noplaylist: false  # Override default to download all videos
```

**Additional options:**
- See [`yt_dlp/YoutubeDL.py`](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py) for full list of options
- Any yt-dlp option can be passed through service data

### Via [`yt_dlp-card`](https://github.com/keywork/yt_dlp-card)

The card includes a checkbox to download full playlists when needed.
