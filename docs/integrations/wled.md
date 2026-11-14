# WLED

CAVE controls WLED light strips directly on your network. Commands and status never leave your home.

## Add a device

1. Open **Devices** and choose **Add device**, then **Set up** next to WLED.
2. Type the strip's address, like `192.168.1.50`, and choose **Check**. CAVE shows the name and chip it reports.
3. Choose **Add**. The strip appears in Devices as a light, plus a preset choice next to it. You can rename them, put them in a room and use them on dashboards and in automations.

To take a strip out of CAVE, open **Add device** again and choose **Remove**.

## What CAVE stores

The strip's address, name and hardware address. WLED needs no password here, so CAVE keeps nothing secret.

## What works today

- On, off and brightness.
- Choosing a preset by name. The list is read from the strip, so a preset you add or rename in WLED shows up within 15 seconds.
- Status is read every 15 seconds, so a change made in WLED's own app can take that long to show.
- Colour and effects aren't offered yet; use a preset for those.

## If something's wrong

- **Check says it doesn't look like WLED:** make sure the address is the strip's, and that WLED is version 0.13 or newer.
- **A strip reads as not responding after working before:** it may have a new address, or lost its Wi-Fi. A DHCP reservation on your router keeps the address stable. If the address did change, add the strip again at its new address, which updates it instead of making a copy.
