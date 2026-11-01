# Install CAVE on Debian 13

CAVE runs on your own machine, with Docker Compose. Once it's installed, nothing it does needs the internet.

## What you need

- **The machine:** Debian 13 "trixie", on a 64-bit PC (amd64) or a 64-bit ARM board such as a Raspberry Pi 4 or 5 (arm64).
- **Memory:** 2 GB of RAM.
- **A fixed address on your network:** a DHCP reservation on your router is fine. Tablets and devices find CAVE by this address.
- **Internet, but only while installing:** it downloads the parts the images are built from.

## 1. Install Docker

Debian's own packages are enough:

```bash
sudo apt update
sudo apt install docker.io docker-compose docker-buildx git
sudo usermod -aG docker $USER
```

Sign out and back in so the `docker` group applies. `docker compose version` should then print a version.

## 2. Get CAVE and install it

```bash
git clone <CAVE repository URL> cave
cd cave
deploy/install.sh
```

The installer asks before it starts, and builds with both parts by default:

- `mqtt`: the Mosquitto broker your devices connect to
- `scripts`: the sandbox that runs PowerShell, Python and Bash scripts

Choose others with `--profiles mqtt` or `--profiles scripts`.

It creates these, all inside the `cave` folder:

| What | Where |
| --- | --- |
| Settings (your network range, this machine's names, which parts run) | `.env` |
| The database, the HTTPS certificate, Mosquitto's data | `data/` |
| Your dashboards, automations, routines and scripts | `config/` |
| Random passwords and tokens, readable only by the containers | `secrets/` |

It then builds and starts everything, and prints three lines you need:

```
CAVE is running at https://192.168.1.20:8443
Certificate fingerprint (SHA-256): 3F:9A:…
CAVE isn't set up yet. Open it in a browser and use this one-time setup code: 7KQ2-M9XD-…
```

**Running the installer again changes nothing that already exists.** It never replaces your data, config, passwords or settings.

If it says the default route goes through a Docker network, it couldn't tell your home network apart from Docker's. Give it your network and this machine's address, then run it again:

```bash
CAVE_LOCAL_RANGES=192.168.1.0/24 CAVE_HOST_IPS=192.168.1.20 deploy/install.sh
```

## 3. Sign in for the first time

1. Open the address the installer printed.
2. Your browser warns about the certificate, because CAVE made it itself. Check that the fingerprint the browser shows matches the installer's, then continue.
3. Enter the setup code, create the owner account, and set up your authenticator app.

The [console guide](../console.md) explains the rest.

## 4. Connect devices

Point Zigbee2MQTT, Tasmota, Shelly or ESPHome at this machine's address, port **1883**.

Each device signs in with its own user name and password. Add one per device:

```bash
docker run --rm -it -v "$PWD/secrets/mosquitto_passwd:/passwd" $(docker compose config --images mosquitto) \
  mosquitto_passwd /passwd kitchen-plug
sudo chown 1883:1883 secrets/mosquitto_passwd && sudo chmod 0400 secrets/mosquitto_passwd
docker compose restart mosquitto
```

Devices that announce themselves show up in **Devices** on their own. The [MQTT guide](../integrations/mqtt.md) has the settings for each kind.

## 5. Scripts

Scripts are files in `config/scripts`. They run only in the sandbox container:

- as their own user
- with a memory and CPU limit
- with no access to CAVE's files or the Docker socket

See the [scripts guide](../scripts.md).

## Running without the internet

CAVE works with the internet unplugged:

- After a power cut or reboot, `docker compose up -d` starts everything again (the containers also restart by themselves).
- No downloads happen: the images are already built, and Mosquitto's image was fetched while installing.

Only installing and upgrading need the internet.

## Upgrade

```bash
cd cave
git pull
deploy/install.sh
```

The installer rebuilds the images and restarts CAVE. Your data, config, passwords and settings are kept. Database changes apply by themselves when CAVE starts.

## Back up and restore

There's no backup screen yet. To back up:

1. Stop CAVE, then copy four things somewhere safe:

   ```bash
   docker compose down
   sudo tar czf cave-backup.tgz data config secrets .env
   docker compose up -d
   ```

2. To restore, unpack those into a fresh `cave` folder and run `deploy/install.sh`. It keeps what it finds.

The backup holds your passwords and tokens: keep it as private as the machine itself.

## Use your own certificate

Browsers warn about CAVE's own certificate. Some tablets won't keep a screen key without a trusted one (see [tablets](tablets.md)). To use a certificate for a real domain, choose one of these:

- **Give it to CAVE:**
  1. Put `fullchain.pem` and `privkey.pem` in `data/tls-own/`.
  2. Run `sudo chown -R 10001:10001 data/tls-own`.
  3. Add these two lines to `.env`, then run `docker compose up -d`:

     ```
     CAVE_CERT=/data/tls-own/fullchain.pem
     CAVE_KEY=/data/tls-own/privkey.pem
     ```

- **Or put a reverse proxy in front:** the proxy terminates HTTPS and forwards to CAVE. Then list the proxy's address under **System › Networks › Trusted proxies**, so CAVE sees each device's real address.

## When every device shows the same 172.x address

Look at **Sign-in log**. If every sign-in comes "from" an address like `172.18.0.1`, the requests are reaching CAVE through Docker's own proxy, not directly. CAVE can't tell which devices are on your network then, so **"Local network only" items are refused for everyone**. It fails safe, never open.

Docker does this for IPv6 connections, and on some setups for IPv4 too. To fix it, use CAVE's IPv4 address, or turn off Docker's userland proxy:

1. Add `{ "userland-proxy": false }` to `/etc/docker/daemon.json`.
2. Run `sudo systemctl restart docker`.

## Uninstall

```bash
cd cave
docker compose down
cd .. && sudo rm -rf cave
```

The last line deletes your data, config and passwords for good. Back up first if you might want them.
