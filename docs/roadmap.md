# CAVE roadmap after Phase 1

Phase 1 is done: Plan 7's exit gate is merged (see [exit-gate.md](exit-gate.md)). This page assigns what's still open to later phases. It follows the [Phase 1 design](superpowers/specs/2026-10-25-cave-phase1-design.md)'s outline, which replaces the phase table in the [design framework](CAVE-Design-Framework.md) where the two differ.

Items marked *(code)* come from `shortcut:` comments in the source; each comment names its limit and when to upgrade it.

## Before Phase 2 starts

- Merge the script access fix (PR 6). Then switch the dashboard builder's (PR 5) script button over to `cave.access.evaluate.can_run_script`, or it lets Scripts section holders past a script's restrictions.
- Settle the "Open before going public" items in the Phase 1 design: the name and trademark check for "CAVE", and the GitHub account to publish under. The repository is already public.
- Never push local branches made before commits switched to the GitHub no-reply address (for example `backup/before-noreply`); they carry a personal email address.
- The Phase 1 plans' checkboxes were never ticked. Treat the merged code and the exit gate as the record, not the checklists.

## Phase 2: first integrations

From the Phase 1 design: the first batch of integrations, picked by research from a fresh list of 30 open, popular, local integrations, plus a setup-wizard network scan.

- **Research and spec:** build the list of 30, pick the first batch, and write the Phase 2 spec and plans (brainstorm, spec, plans, as Phase 1 did).
- **Integration hosts:** the framework runs integrations outside the core. MQTT and Kasa run in the core today; decide in the Phase 2 spec whether new integrations move out, and whether those two follow.
- **Kasa:** the framework's GPL warning about python-kasa no longer applies, because CAVE has its own client. Still open *(code)*: only KLAP devices are offered (older and Tapo-only encryption need their own client); networks wider than /22 aren't scanned; a plug that changes address reads as unavailable until the next scan.
- **Setup wizard network scan:** build on the Kasa LAN scan rather than starting over.
- **Notifications:** ntfy and SMTP targets beyond the built-in `notify.cave`, as the Phase 1 design says.
- **Device registry:** MQTT device details live on entity attributes until a registry exists *(code)*. The console shows room slugs in words instead of area names *(code)*.
- **Console speed:** the main bundle is about 990 kB (279 kB gzipped), and every viewer downloads it, wall tablets included. Load the admin pages on demand; the editor (Monaco) already loads separately.
- **Scripts page:** it requests run history once per script to show the last outcome. Return the last outcome from `GET /scripts` instead.
- **Editors:** warn before leaving the automation, dashboard or script editor with unsaved changes.

## Phase 3 and later

From the Phase 1 design: SSO, passkeys, SSH and CAVE-host script targets, the visual builder, history, backups, native packages, the remaining integrations, and an optional local CA. Also assigned here:

- **Secrets storage:** encrypt authenticator (TOTP) secrets with a host key; today they're stored unencrypted *(code)*.
- **Sign-in:** half-finished MFA sign-ins are kept in memory and lost on restart *(code)*; move them to the database with SSO and passkeys.
- **People:** an account's expiry can't be cleared once set *(code)*.
- **Settings:** a General page for time zone and similar settings; Phase 1 takes the time zone from the host *(code)*.
- **Dashboards:** the dashboard editor's preview shows the saved version, not the draft *(code)*. The visual builder (PR 5) is ahead of this phase.
- **Script targets:** SSH and CAVE-host targets. The Windows process cleanup is a development convenience only *(code)*; Debian is the target.
- **Networks:** local ranges are found from the one outbound interface; Admins add others by hand *(code)*.
- **Translation framework:** dates and times use one built-in English format ("23 Oct, 14:02"). Move to `Intl.DateTimeFormat` when the console is translated.
