# Shelly

CAVE controls Shelly relays directly on your network, both older (generation 1) and newer (Plus and Pro) models. Commands and status never leave your home.

## Add a device

1. Open **Devices** and choose **Add device**, then **Set up** next to Shelly.
2. Type the device's address, like `192.168.1.60`, and choose **Check**. CAVE shows the model and name it reports.
3. Choose **Add**. Each relay appears in Devices as a switch. Where the device measures them, power (W) and energy (kWh) appear as sensors. You can rename them, put them in a room and use them on dashboards and in automations.

To take a device out of CAVE, open **Add device** again and choose **Remove**.

## What CAVE stores

The device's address, name and hardware address. CAVE keeps nothing secret, because Shelly devices with a password aren't supported yet.

## What works today

- Switching each relay on, off or toggling it.
- Power and energy, where the device reports them. Energy is a running total since the device last reset it.
- Status is read every 15 seconds, so a change made at the wall switch or in Shelly's own app can take that long to show.

## If something's wrong

- **"This Shelly has a password set":** CAVE can't use password-protected Shelly devices yet. Open the device's own web page, turn off the login under its security settings, then add it again. Only do this on a network you trust.
- **"CAVE supports Shelly relays for now, not dimmers or colour lights":** the device is a dimmer or a colour light (for example a Shelly Dimmer or RGBW). CAVE can't control those yet.
- **A device reads as not responding after working before:** it may have a new address or lost its Wi-Fi. A DHCP reservation on your router keeps the address stable. If it did change, add the device again at its new address, which updates it instead of making a copy.
