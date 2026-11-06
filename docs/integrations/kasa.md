# TP-Link Kasa

CAVE controls Kasa plugs and switches directly on your network. Commands and status never go through TP-Link's cloud.

## Add a device

1. Open **Devices** and choose **Add device**. CAVE looks for Kasa devices on your local network ranges.
2. Sign in with the email and password from your Kasa app. Current Kasa firmware only takes commands from the account a device is set up with, so this is needed even though everything stays local. You only do this once.
3. Choose **Add** next to each device. It appears in Devices under the name it has in the Kasa app, and you can rename it, put it in a room and use it on dashboards and in automations.

To take a device out of CAVE, open **Add device** again and choose **Remove**.

## What CAVE stores

CAVE keeps a hash of your TP-Link sign-in, the form the devices check against, in its database. It never stores your password. The hash is enough to control your Kasa devices, so protect CAVE's data folder and backups. It can't be used to sign in to your TP-Link account.

Changing your TP-Link password means signing in again: the panel asks when your devices stop accepting the old one.

## What works today

- On and off for plugs and switches, including dimmers (KS225 and similar), which act as plain on/off for now.
- Status is read every 30 seconds, so a change made at the wall or in the Kasa app can take that long to show.
- Devices that use KLAP encryption, which is all current Kasa firmware. Older firmware and Tapo-only encryption aren't offered yet.

## If something's wrong

- **No devices found:** the scan covers the local ranges under **Network and certificate**, for ranges of /22 or smaller. Check the plug's network is listed.
- **A device reads as not responding after working before:** its address may have changed. Open **Add device** to scan again, which picks up the new address. A DHCP reservation on your router stops this happening.
