# Wall tablets (screens)

A **screen** is a tablet that signs in as itself, with no person, and sees only the dashboards assigned to it. For example, "Garage tablet" opens "Garage Door Control", and only while it's on your home network.

When a tablet is set up, its browser makes a key that it can never export, not even to CAVE's own code. Each time the tablet connects, CAVE asks it to sign a fresh, single-use challenge with that key. Copying the tablet's files or recording its traffic doesn't let anyone else pass as it.

## Which browsers work

This works only if the browser keeps that key on a page served with CAVE's self-signed certificate. The **tablet check** page at `/spike` tests exactly that.

| Browser | Device and OS | Secure context | Key made and stored | Kept after reload | Not exportable | Signs | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Chromium 152 (Claude desktop browser pane) | Windows 11, over `localhost` | Pass | Pass | Pass | Pass | Pass | Works. This checks the script only, not the self-signed certificate case. |
| Safari | iPad (iPadOS) | not yet tested | | | | | |
| Chrome | Android tablet | not yet tested | | | | | |
| Silk | Amazon Fire tablet | not yet tested | | | | | |

If a browser fails "Kept after reload" or "Signs" on the self-signed certificate, that tablet needs **your own certificate** (see below) before it can be enrolled.

## Run CAVE for testing

Until the Docker Compose install arrives, run CAVE from a checkout:

```bash
cd core
../.venv/bin/python -m cave serve --data ../data
```

On Windows, use `..\.venv\Scripts\python`. CAVE prints its address (for example `https://192.168.1.20:8443`) and its **certificate fingerprint**. CAVE serves HTTPS only; there's no plain-HTTP address.

## Run the tablet check

1. On the tablet, open `https://<CAVE address>:8443/spike`.
2. The browser warns that the certificate isn't trusted. Before accepting, open the certificate details and check that its SHA-256 fingerprint matches the one CAVE printed. If they don't match, stop: something else is answering on that address.
3. Accept the warning once.
4. Tap **Reload and check again**, then screenshot the table.

## Enroll a tablet

1. An Admin adds the screen under **Users and permissions › Screens** (`POST /api/v1/screens` until the console arrives). CAVE gives a one-time link that works for **10 minutes**.
2. Open the link on the tablet. The tablet shows a **screen fingerprint** and waits.
3. The Admin checks that the fingerprint matches the one in Screens, then selects **Approve**. The tablet signs in by itself within a few seconds.
4. Assign the tablet to a dashboard, and set that dashboard to **Local network only** if it should work only at home.

Revoking a screen deletes its key and closes its open connections at once. Re-enrolling needs a new link.

> **Not yet possible from a browser alone:** the admin console and first-run setup arrive in a later phase. Until then, the steps above go through the API.

## Using your own certificate

A certificate your devices already trust removes the warning, and makes enrollment work on any browser that failed the check above.

- **Directly:** `python -m cave serve --cert /path/fullchain.pem --key /path/privkey.pem`
- **Behind a reverse proxy** (Nginx, Caddy): let the proxy handle HTTPS, and add the proxy's address under **System › Networks › Trusted proxies**. If you don't, CAVE sees every request as coming from the proxy, and won't believe the forwarded client address.

A real domain with a DNS-challenge certificate (Caddy and certbot both support this) works on a home network with no ports opened to the internet.
