# Philips Hue

CAVE controls Hue lights and reads Hue motion and temperature sensors through the Hue bridge on your network. Commands and status never leave your home.

## Add a bridge

1. Open **Devices** and choose **Add device**, then **Set up** next to Philips Hue.
2. Type the bridge's address, like `192.168.1.70`, and choose **Check**. CAVE shows the bridge's model and name.
3. Press the round button on top of the Hue bridge, then choose **Add** within 30 seconds. If you were too slow, CAVE says "Press the button on the Hue bridge first, then choose Add again." Press the button and try again.
4. Each light, motion sensor and temperature sensor on the bridge appears in Devices. You can rename them, put them in a room and use them on dashboards and in automations.

To take a bridge out of CAVE, open **Add device** again and choose **Remove**.

## What CAVE stores

The bridge's address, name and hardware address, and the bridge key CAVE received when you pressed the button. The key is saved encrypted. It is never shown again, not in the panel, the audit log or the logs.

## What works today

- Lights: on, off, toggle and brightness. Colour isn't supported yet.
- Motion sensors (on when motion is seen) and temperature sensors (in °C).
- Status is read every 15 seconds, so a change made in the Hue app or at a wall switch can take that long to show.
- Lights or sensors you add to the bridge later appear within 15 seconds. One removed from the bridge reads as not available until you remove the bridge from CAVE.
- A light that is switched off at the wall (the bridge can't reach it) reads as not available.

## If something's wrong

- **"Press the button on the Hue bridge first":** the button wasn't pressed in the last 30 seconds. Press it and choose **Add** again.
- **Everything from the bridge reads as not available, and the log says the key can't be read:** CAVE's own encryption key was replaced, so the saved bridge key can't be opened. Remove the bridge and add it again.
- **A bridge reads as not responding after working before:** it may have a new address or lost its network cable. A DHCP reservation on your router keeps the address stable. If it did change, add the bridge again at its new address, which updates it instead of making a copy.
