[![Discord](https://badgen.net/discord/online-members/zGVYf58)](https://discord.gg/zGVYf58)
![GitHub Release](https://img.shields.io/github/v/release/jackjpowell/uc-intg-jvc)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/jackjpowell/uc-intg-jvc/total)
<a href="#"><img src="https://img.shields.io/maintenance/yes/2025.svg"></a>
[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee&nbsp;☕-FFDD00?logo=buy-me-a-coffee&logoColor=white&labelColor=grey)](https://buymeacoffee.com/jackpowell)

# Lutron Caseta integration for Remote Two

Using [uc-integration-api](https://github.com/aitatoi/integration-python-library)

This integration allows you to control your Lutron Caseta lights and covers from your Unfolded Circle Remote.

## Light
Supported attributes:
- State

Supported commands:
- Turn on & off
- Brightness

## Cover
- Up
- Down
- Toggle

## Usage
The simpliest way to get started is by uploading this integration to your unfolded circle remote. You'll find the option on the integration tab in the web configurator. Simply upload the .tar.gz file attached to the release. This option is nice and doesn't require a separate docker instance to host the package. However, upgrading is a fully manual process. To help with this, a docker image is also provided that allows you to run it externally from the remote and easily upgrade when new versions are released. 

### Install on Remote

- Download tar.gz file from Releases section of this repository
- Upload the file to the remove via the integrations tab (Requires Remote firmware >= 2.0.0)

### Docker
```
docker run -d --name=uc-intg-lutron --network host -v $(pwd)/<local_directory>:/config --restart unless-stopped ghcr.io/jackjpowell/uc-intg-lutron:latest
```

### Docker Compose
```
services:
  uc-intg-lutron:
     image: ghcr.io/jackjpowell/uc-intg-lutron:latest
     container_name: uc-intg-lutron
     network_mode: host
     volumes:
       - ./<local_directory>:/config
     environment:
       - UC_INTEGRATION_HTTP_PORT=9090
     restart: unless-stopped
```
