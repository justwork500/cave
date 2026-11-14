# Fully Kiosk Browser

CAVE turns a Fully Kiosk Browser tablet's screen on and off, sets its screen brightness and reads its battery level. Commands and status never leave your home.

## Turn on Remote Administration

1. In Fully Kiosk, open **Settings**, then **Remote Administration (PLUS)**.
2. Turn on **Enable Remote Administration** and set a **Remote Admin Password**.
3. Note the tablet's address on your home network, like `192.168.1.80`.

## Add a tablet

1. Open **Devices** and choose **Add device**, then **Set up** next to Fully Kiosk Browser.
2. Type the tablet's address and choose **Check**.
3. Type the Remote Administration password and choose **Add**. If it is wrong, CAVE says "That password didn't work. Check Remote Administration in Fully Kiosk's settings."
4. The tablet's screen, brightness and battery appear in Devices. You can rename them, put them in a room and use them on dashboards and in automations.

To take a tablet out of CAVE, open **Add device** again and choose **Remove**.

## What CAVE stores

The tablet's address, name and device id, and the password, saved encrypted. It is never shown again, not in the panel, the audit log or the logs.

Fully Kiosk's remote API is plain HTTP on port 2323 and takes the password in the request, so the password crosses your home network unencrypted each time CAVE talks to the tablet. That is how the app works; keep the tablet on a network you trust.

## What works today

- Screen on and off, screen brightness (0 to 255) and battery level (%).
- Status is read every 15 seconds, so a change made on the tablet can take that long to show.
- Motion isn't available, because Fully Kiosk doesn't report it in its status.

## If something's wrong

- **"That password didn't work":** check the Remote Admin Password in Fully Kiosk's settings.
- **Everything from the tablet reads as not available, and the log says the password can't be read:** CAVE's own encryption key was replaced. Remove the tablet and add it again.
- **A tablet reads as not available after working before:** it may be asleep, off the network, have a new address, or its password may have changed. If the address or password changed, remove the tablet and add it again.
