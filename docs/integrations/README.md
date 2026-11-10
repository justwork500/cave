# Adding a device

Every integration adds devices the same way. Open **Devices**, choose **Add device**, and find the integration in the list. Choose **Set up** next to it.

1. Type the device's address on your home network, like `192.168.1.40`, and choose **Check**. CAVE asks the device what it is and shows its model and name. If nothing answers, or the address isn't on your network, the message appears under the address.
2. Complete the pairing step. It depends on the integration:
   - **Password**, **Encryption key** or **PIN:** type it in the box. The hint under the box says where to find it.
   - **Button:** press the button on the device when the panel asks. There is nothing to type.
   - **Nothing:** some devices need no pairing, and this step doesn't appear.
3. Choose **Add**. The device appears in Devices and you can rename it, put it in a room and use it on dashboards and in automations.

If a device you already added turns up at a new address, adding it again at the new address updates it instead of making a second copy.

## Remove a device

Open **Add device**, choose **Set up** next to the integration, and choose **Remove** beside the device. CAVE asks you to confirm first, then stops controlling it and forgets its saved key.

## What CAVE stores

A password, key or PIN is saved encrypted in CAVE's database. It is never shown again, not in the panel, the audit log or the logs. To change it, remove the device and add it again.

## Integrations

Each integration's page is linked here as it is added. [TP-Link Kasa](kasa.md) and [MQTT devices](mqtt.md) work today.
