# Home Assistant - Ecowitt Official Integration
 

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

 
This integrated uses web interfaces to obtain data from the local network.

## :computer: Installation

### HACS (Preferred)
This integration can be added to Home Assistant as a [custom HACS repository](https://hacs.xyz/docs/faq/custom_repositories):
1. From the HACS page, click the 3 dots at the top right corner.
1. Select `Custom repositories`.
1. Add the URL `https://github.com/Ecowitt/ha-ecowitt-home`
1. Select the category `Integration`.
1. Click the ADD button.
1. Restart Home Assistant
1. Click the button below, or in the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Ecowitt Official Integration"

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Ecowitt&repository=ha-ecowitt-home&category=integration)

### Manual
1. Download the latest release from [here](https://github.com/Ecowitt/ha-ecowitt-home/releases).
1. Create a folder called `custom_components` in the same directory as the Home Assistant `configuration.yaml`.
1. Extract the contents of the zip into folder called `ha_ecowitt_home` inside `custom_components`.
1. Restart Home Assistant
1. Click the button below, or in the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Ecowitt Official Integration"

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Ecowitt&repository=ha-ecowitt-home&category=integration)

## :bulb: Usage
1. The following steps must be performed to set up this integration.
1. Configure gateway devices to your LAN using the WSView Plus app or Ecowitt app on your phone and then view the device IP address.
1. Enter the IP address of the device in the integration, and the integration will obtain the data of the gateway device after a successful connection.

![Step 1](./img/20240223161726.png)
![Step 2](./img/20240223161811.png)
