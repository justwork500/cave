# CAVE Phase 1 · Plan 6: Console and dashboards — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Frontend tasks also load the `frontend-design:frontend-design` skill before writing UI.

**Goal:** People use CAVE in a browser.
- A first-run setup creates the owner, with an authenticator app.
- Everyone lands on an **Actions dashboard** in plain words, where controls they can't use show as locked.
- People allowed into the **admin console** manage devices and rooms, users and permissions (including screens with a QR code), automations (with the sentence builder, recipes and the Test Center), scripts, dashboards and system settings.

**Architecture:**
- **Part A (Python) fills the API gaps the console needs:**
  - first-run setup and authenticator enrollment
  - rooms, and renaming devices
  - a per-viewer *rendered dashboard* endpoint, so access, restricted stubs and markdown templates are decided on the server, never in the browser
  - a Home summary, and the sign-in log
  - serving the built console as a single-page app with a strict Content-Security-Policy
- **Part B (TypeScript) is the console itself:** React 19, Fluent UI React v9, TanStack Query, react-router and Vite, in `console/`. It's built to static files that the core serves. Node is needed only to build it, never at runtime.

**Tech Stack:**
- Python side as before.
- Console: Node 22 LTS + pnpm (via corepack), React 19, TypeScript (strict), `@fluentui/react-components` v9, `@tanstack/react-query`, `react-router`, Vite, Monaco (`@monaco-editor/react` + `monaco-yaml`, schema validation against `/api/v1/schemas`), `qrcode` (screen enrollment QR codes).
- Tests: Vitest, React Testing Library, `vitest-axe`.

**Spec:** `docs/superpowers/specs/2026-10-25-cave-phase1-design.md`: "Console sections in Phase 1", "Actions dashboard", "Test Center", "Screens", "The access model", and the scope rows "Console" and "Dashboards". Background: the framework's "User experience" (friendly-by-default rules, words we use), "Navigation, sign-in and permissions" (menu bar, addresses), "Admin console" (page patterns). Mockups: `design/admin-console/*.dc.html` (Main, Dashboard, Devices, Automation, Scripts, Users, Login, SimpleHome). This builds on Plans 1–5, all on `main`.

**Prerequisite (a human step):** Node 22 LTS must be installed on the dev machine, for example with `winget install OpenJS.NodeJS.LTS`, then `corepack enable`. It isn't installed today. Part A doesn't need it.

## Global Constraints

- Everything in Plans 1–5's Global Constraints still holds.
- **The server decides.** The browser never works out access or hides restricted data on its own. It shows what the API returns: restricted stubs, locked items, rendered markdown. Hiding a menu entry is only cosmetic.
- **Words** follow the framework's "Words we use" table in the UI: Device, Control or reading, Room, Connection, Automation, Routine, Script. Entity IDs appear only in Advanced views and editors.
- **Friendly by default:**
  - every error says what happened and what to do next, using the API's `detail` text
  - risky actions (delete, running a script, revoking a screen) ask for confirmation and say what will change
  - every page has a help link to its docs page
- **Accessible:**
  - full keyboard use and screen-reader labels
  - text contrast of at least 4.5:1
  - light, dark and high-contrast themes
  - every screen works at 360 px wide
  - every page component has an axe test with no violations
- **Brand:** CAVE's own name, logo and colours, from the mockups (`#0B6A8A` brand, `#1C2830` top bar). No Microsoft logos or product names. Fluent UI is the component library, not the look.
- **Security headers on every console response:**
  - `Content-Security-Policy: default-src 'self'; connect-src 'self' wss:; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: no-referrer`

  The console uses no third-party CDNs.
- **Addresses:**
  - `/`: your default dashboard
  - `/d/<slug>`
  - `/admin/...`
  - `/login`
  - `/setup`
  - `/enroll`, `/spike`: already exist

  Unknown non-API paths serve the SPA. `/api/*` and `/static/*` are never shadowed.
- **No new Python dependencies.** The console's npm dependencies are pinned exact in `console/package.json` with a committed `pnpm-lock.yaml`.

## Review Focus

1. **A restricted device on a dashboard the viewer can open** (a tile for the garage on the Kids dashboard, or a markdown card reading `states('cover.garage_door')`) → the rendered view shows a locked tile and `restricted` in the markdown. The live feed never sends that device's state. Pinned in Task 3.
2. **The first-run setup endpoint reached by someone else on the LAN before the owner** → refused without the one-time setup code printed on the server console. Once any user exists, it's refused for good, even with the code. Pinned in Task 1.
3. **The console shell for a household member** → no admin link and no admin routes. A typed `/admin/users` URL shows a friendly "You don't have access" page, and the API refuses every call anyway. Pinned in Tasks 5, 6 and 9.
4. **Script and YAML text containing `</script>`, HTML or `{{ }}`** in the editors, or a markdown card with HTML → shown as text. Markdown is rendered without raw HTML. Nothing executes in the page. Pinned in Tasks 7 and 9.
5. **A phone at 360 px, keyboard-only use, and the high-contrast theme** on the dashboard, sign-in and Access table → usable with no horizontal scroll, every control reachable and labelled. Pinned in Tasks 6, 7 and 8.

---

## File structure

```text
core/cave/migrations/0006_console.sql      # setup code, areas, entity overrides
core/cave/api/setup.py                     # first-run setup, MFA enrollment, password change
core/cave/api/areas.py                     # rooms, renaming devices
core/cave/api/views.py                     # rendered dashboards, Home summary, sign-in log
core/cave/api/console.py                   # serve the built console (SPA fallback, headers)
core/cave/api/entities.py                  # entity_view applies overrides
core/cave/__main__.py                      # prints the setup code on first start
console/package.json  pnpm-lock.yaml  vite.config.ts  tsconfig.json  index.html
console/src/api/        client.ts  ws.ts  types.ts
console/src/app/        App.tsx  routes.tsx  shell/  theme.ts
console/src/pages/      Login  Setup  Profile  Dashboard  NoAccess
console/src/admin/      Home  Devices  Users  Groups  Screens  Access  Tokens  Audit  SignIns
                        Automations  SentenceBuilder  recipes.ts  Traces  TestCenter
                        Scripts  Dashboards  Networks  Certificate
console/src/cards/      Tile  Entities  Gauge  Button  Markdown
.github/workflows/console.yml
docs/console.md
```

---

# Part A — the API the console needs (Python)

### Task 1: First-run setup, authenticator enrollment, and changing your password

**Files:**
- Create: `core/cave/migrations/0006_console.sql` (the whole plan's tables), `core/cave/api/setup.py`
- Modify: `core/cave/api/auth.py`, `core/cave/__main__.py`, `core/cave/api/app.py`
- Test: `core/tests/test_setup.py`

**Interfaces:**
- Tables in `0006`:
  - `setup_code(code_hash TEXT NOT NULL)`, which has at most one row
  - `areas(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, floor TEXT)`
  - `entity_overrides(entity_id TEXT PRIMARY KEY, name TEXT, area_id TEXT REFERENCES areas(id) ON DELETE SET NULL)`
- Produces in `setup.py`:
  - `ensure_setup_code(db) -> str | None`. When there are no users and no code, it creates a 4×4 grouped code from `secrets` (e.g. `7KQ2-M9XD-…`), stores its SHA-256, and returns it. Otherwise it returns `None`. `create_app` calls it, and `cave serve` prints the code when one was just created. `shortcut: the code shows only on the first start's console; lost codes need deleting the setup_code row by hand`.
  - `GET /api/v1/setup` → `{"needed": bool}`
  - `POST /api/v1/setup {code, username, password (min 12), display_name}`:
    - In one transaction, it refuses with **409** if any user exists, and with **403** `"That setup code isn't right."` if the code doesn't match (`hmac.compare_digest` on the hashes).
    - Otherwise it creates the Admin, runs `setup_totp`, deletes the code, and audits `setup.owner_created`.
    - It returns `{"provisioning_uri", "recovery_codes"}` and sets the `cave_pending` MFA cookie, so the existing `POST /auth/mfa` finishes sign-in.
- Modifies sign-in: when `mfa_required(user)` and the user has **no** TOTP yet (for example an Operator an Admin just created), `/auth/login` returns `{"mfa_required": true, "mfa_setup": true}`. `POST /api/v1/auth/mfa/setup` (pending cookie only, user without TOTP) returns `{"provisioning_uri", "recovery_codes"}`, and `/auth/mfa` then finishes as usual.
- `GET /api/v1/me` adds `has_totp` and `sections` (the IDs of console sections the caller may use, from `evaluate`), so the shell knows what to draw.
- `POST /api/v1/me/password {current, new}` (min 12) → 204. A wrong `current` counts toward lockout. Other sessions of the user end, and it's audited `user.password_changed`.

- [ ] **Step 1: Write failing tests:**
  - `test_setup_needed_only_without_users`
  - `test_setup_code_required` (Review Focus 2: no code → 422, wrong code → 403, right code → 200 and an Admin exists)
  - `test_setup_refused_once_a_user_exists` (Review Focus 2: even with a fresh code)
  - `test_setup_then_mfa_signs_in`
  - `test_concurrent_setup_one_wins` (two threads → exactly one 200)
  - `test_operator_without_totp_enrolls_at_login`
  - `test_mfa_setup_needs_pending_and_no_totp`
  - `test_me_lists_sections` (operator → devices/automations/scripts/dashboards; household → none)
  - `test_password_change_ends_other_sessions`
  - `test_serve_prints_setup_code_once` (call `ensure_setup_code` twice → the code first, then `None`)
- [ ] **Step 2:** Run `cd core && ../.venv/Scripts/python -m pytest -q tests/test_setup.py`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite with `-W error`, `ruff check .` and `mypy --strict cave`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(auth): first-run setup, authenticator enrollment, password change"`

---

### Task 2: Rooms, and renaming devices

**Files:**
- Create: `core/cave/api/areas.py`
- Modify: `core/cave/api/entities.py` (`entity_view` applies overrides)
- Test: `core/tests/test_areas.py`

**Interfaces:**
- `GET /api/v1/areas` (any signed-in principal: room names aren't secret) → `[{id, name, floor}]`
- `POST`, `PATCH /{id}` and `DELETE /{id}` on `/api/v1/areas` need `section:devices` and are audited `area.*`. The ID is a slug of the name, with `_2`… on collision.
- `PATCH /api/v1/entities/{entity_id} {name?, area_id?}` needs `section:devices` **and** `can_control`, so you can't rename what you can't control (a stub stays a stub). It upserts `entity_overrides`, publishes `access_changed` (so sockets refresh their names), and is audited `entity.update` with old and new values.
- `entity_view` (and so `/states`, the WebSocket and dashboard views) uses the override's name and area when present, otherwise the integration's own. That includes the restricted stub, whose name and room people may see.

- [ ] **Step 1: Write failing tests:**
  - `test_area_crud_and_audit`
  - `test_rename_and_assign_room_shows_everywhere` (`/states` and a stub both show the new name and area)
  - `test_rename_needs_control`
  - `test_household_cannot_create_areas`
  - `test_deleting_area_clears_entity_area`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(devices): rooms and renaming devices"`

---

### Task 3: Rendered dashboards, the Home summary, and the sign-in log

**Files:**
- Create: `core/cave/api/views.py`
- Test: `core/tests/test_views.py`

**Interfaces:**
- `GET /api/v1/dashboards/{slug}/view` needs `use` of `dashboard:<slug>` (screens included). It returns the dashboard with every card resolved **for this viewer**:
  - `tile`, `gauge`: the card plus `"entity": entity_view(...)`, which is the restricted stub when the viewer can't control it. A stub tile is `"locked": true`.
  - `entities`: a list of `entity_view`s.
  - `button` with `action`: `{"allowed": evaluate(action item).allowed, "listed": …}`. It's omitted when not listed.
  - `button` with `entity`/`command`: `"allowed": can_control(...)`.
  - `markdown`: `"html": None` and `"text": render(content, {}, ViewerReader, now)`. `ViewerReader.get` returns a state of `"restricted"` (and no attributes) for entities the viewer can't control. A template error renders as `"(this card couldn't be shown)"`, and is logged.
  - The viewer's default dashboard is whichever comes first of: `home` if allowed, then the first allowed dashboard by title. It's shown by `GET /api/v1/dashboards/default` → `{"slug": … | null}`.
- `GET /api/v1/summary` returns only the tiles the caller's sections allow:
  - `mqtt`: `{status, entities}`, with `section:devices` or `section:system`
  - `unavailable`: a count of entities the caller **can control** whose state is `unavailable`, with `section:devices`
  - `failures_24h`: a count of automation traces with outcome `failed` in the last 24 h, with `section:automations` or `section:run_history`
  - `screens_pending`: with `section:users`

  Absent keys mean "not yours to see".
- `GET /api/v1/signin-log?limit=` (`section:signin_log`, default 100, max 1000) → `[{username, at, ok, ip}]`, newest first. `ok` is shown as `"signed in"`, `"wrong password or code"` or `"blocked (too many tries)"`.

- [ ] **Step 1: Write failing tests**, using the Plan 1 garage fixture plus a `kids` dashboard file that holds a tile for `cover.garage_door` and a markdown card reading it:
  - `test_view_locks_restricted_tile_and_markdown` (Review Focus 1: sam sees `locked`, the stub, `restricted` in the text, never `open`/`closed`)
  - `test_view_needs_dashboard_use` (403)
  - `test_screen_gets_its_dashboard_view`
  - `test_button_allowed_flags`
  - `test_default_dashboard_choice`
  - `test_summary_only_your_tiles` (operator vs household vs admin)
  - `test_signin_log_permission_and_labels`
  - `test_markdown_template_error_is_friendly`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(api): rendered dashboards, home summary and sign-in log"`

---

### Task 4: Serving the console

**Files:**
- Create: `core/cave/api/console.py`
- Modify: `core/cave/api/app.py` (include it **last**), `core/pyproject.toml` (package data `web/console/**`)
- Test: `core/tests/test_console_serving.py`

**Interfaces:**
- The built console lives in `core/cave/web/console/`, produced by `pnpm build` (Task 5 sets Vite's `outDir` there). It's not committed: `.gitignore` it, and Plan 7's image build runs `pnpm build`.
- `GET /assets/*` is served from the build with `Cache-Control: public, max-age=31536000, immutable`, since Vite's file names are hashed.
- Any other GET that isn't under `/api/`, `/static/`, `/assets/`, `/enroll` or `/spike` returns `index.html` with `Cache-Control: no-store`.
- When the build is missing, it returns a plain page: "The console hasn't been built. Run `pnpm --dir console build`."
- A middleware adds the Global Constraints' security headers to every non-API response.

- [ ] **Step 1: Write failing tests**, with a fake build written into a temporary `web/console` via a monkeypatched path:
  - `test_spa_fallback_for_client_routes` (`/`, `/d/kids`, `/admin/users` → `index.html`)
  - `test_api_routes_not_shadowed` (`/api/v1/health` still JSON; unknown `/api/v1/nope` → 404 JSON, not HTML)
  - `test_assets_cached_index_not`
  - `test_security_headers`
  - `test_missing_build_message`
  - `test_no_path_escape` (`/assets/../../db.py` → 404)
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(console): serve the built console with strict headers"`

---

# Part B — the console (TypeScript)

Every task in Part B runs `pnpm --dir console lint`, `pnpm --dir console test` and `pnpm --dir console build` as its checks. Every page component gets a test that renders it with mocked API responses (`msw`, or a fetch mock in `src/test/`) **and** an axe check with no violations.

### Task 5: Scaffold, API client, live feed and themes

**Files:**
- Create: `console/` (Vite + React + TS strict + ESLint + Vitest), `console/src/api/client.ts`, `console/src/api/ws.ts`, `console/src/api/types.ts`, `console/src/app/theme.ts`, `.github/workflows/console.yml`
- Modify: `.gitignore` (`console/node_modules`, `core/cave/web/console/`)

**Interfaces:**
- `api.get/post/put/patch/del<T>(path, body?)` uses `fetch` with `credentials: "same-origin"` and JSON. A non-2xx response throws `ApiError {status, detail}`, where `detail` comes from the response's `detail`, or "Something went wrong. Try again." `401` sends you to `/login?next=…`, except on `/login` and `/setup` themselves.
- `useLive()` is one WebSocket per tab to `/api/v1/ws`. It subscribes to `state_changed`, reconnects with backoff (1, 2, 4 … 30 s), and on reconnect refetches the current queries. It exposes `onState(entityId, cb)` and `onNotification(cb)`. Closes with 4401 send you to `/login`, and 4408 resyncs.
- `types.ts` mirrors the API shapes this plan uses: `EntityView`, `RestrictedStub`, `DashboardView`, `Card*`, `Item`, `Trace`, `Me`, and the rest.
- Themes are Fluent `webLightTheme`, `webDarkTheme` and `teamsHighContrastTheme`, re-coloured with CAVE's brand ramp. The choice follows the OS until the user picks one in their profile (kept in `localStorage`, read in try/catch).
- CI (`console.yml`) runs on Node 22 with `corepack enable`: `pnpm install --frozen-lockfile`, lint, test, build.

- [ ] **Step 1: Write failing tests:**
  - `client.test.ts`: `ApiError` carries the server's `detail`; 401 redirects with `next`; 204 returns `undefined`
  - `ws.test.ts`: backoff schedule; resubscribes after reconnect; a 4401 close sends you to `/login`
  - `theme.test.ts`: the brand colour on text meets 4.5:1 against the surface it's used on, in all three themes
- [ ] **Step 2:** Run `pnpm --dir console test`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun the tests, then lint and build. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(console): scaffold, api client, live feed and themes"`

---

### Task 6: Sign-in, setup, profile, and the shell

**Files:**
- Create: `console/src/app/App.tsx`, `routes.tsx`, `shell/MenuBar.tsx`, `shell/Bell.tsx`, `pages/Login.tsx`, `pages/Setup.tsx`, `pages/Profile.tsx`, `pages/NoAccess.tsx`

**Interfaces:**
- **`/setup`:** a wizard following the framework's first steps, cut to Phase 1.
  1. Enter the setup code from the server console.
  2. Create the owner: name, username, a password of 12+ characters, with a strength hint.
  3. Scan a QR code (rendered from `provisioning_uri` with `qrcode`, with the secret also shown as text for typing in), then enter a code.
  4. Show the 10 recovery codes once, with "I've saved these" required before continuing.
- **`/login`:** username and password, then an authenticator code step, or the enrollment step when `mfa_setup` is set. Lockout and wrong-password messages come from the API. Recovery codes are accepted in the code field.
- **Menu bar:** the CAVE logo (back to `/`), a dashboard switcher (the listed dashboards, with locked ones shown as locked), **Admin console only when `me.sections` isn't empty**, the notifications bell (unread count, list, mark read, live via `onNotification`), and your name (profile, theme, sign out).
- **`/profile`:** change password, theme, and your default dashboard (kept in `localStorage`).
- **`NoAccess`:** shown for any admin route whose section isn't in `me.sections` (Review Focus 3).

- [ ] **Step 1: Write failing tests:**
  - `Login.test.tsx`: password → code → in; enrollment path; error text from the API
  - `Setup.test.tsx`: all four steps; recovery codes must be acknowledged
  - `MenuBar.test.tsx`: no admin link for a household user (Review Focus 3); bell count updates on a live notification
  - `routes.test.tsx`: `/admin/users` for a household user shows `NoAccess`
  - axe on each page
  - a test at 360 px wide checking that the menu collapses into a menu button (Review Focus 5)
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun the tests, then lint and build. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(console): sign-in, setup, profile and shell"`

---

### Task 7: The Actions dashboard

**Files:**
- Create: `console/src/pages/Dashboard.tsx`, `console/src/cards/{Tile,Entities,Gauge,Button,Markdown}.tsx`

**Interfaces:**
- **Routes:** `/` loads `GET /dashboards/default`, then the view. `/d/:slug` loads that view.
- **Layout:**
  - each view is a tab, and each section a titled group
  - cards sit on a 12-column grid using each card's `w` and `h`
  - below 600 px wide everything is one column, so there's no horizontal scroll (Review Focus 5)
- **Live state:** values update through `useLive().onState`.
- **The cards:**
  - **Tile:** the name, the room and the state in plain words ("On", "Closed", "21.5 °C"). A tap with `tap_action: toggle` sends `toggle` through the command API. When `locked`, it shows a lock icon and "Restricted", takes no action, and still has a screen-reader label.
  - **Entities:** a list of tile rows.
  - **Gauge:** an SVG arc with the value and unit, and severity colours with text labels, not colour alone.
  - **Button:** the name, plus the last-run hint the API gives. `confirm` opens a dialog saying what will run. It runs the action through `POST /{automations|sequences}/{id}/run`, or sends the entity command. A success or failure toast uses the API's text.
  - **Markdown:** the server-rendered `text`, shown through a tiny renderer that supports headings, bold/italic, lists and links, and **ignores raw HTML** (Review Focus 4). No `dangerouslySetInnerHTML`.

  Errors read like the framework's example: "The garage door didn't respond. Check it's powered on, then try again."
- **Kiosk use:** a screen (signed in by its key) lands on `/` with no admin link and its assigned dashboard. That already works through `me`.

- [ ] **Step 1: Write failing tests:**
  - `Dashboard.test.tsx`: each card type from a fixture view; a locked tile has no button role and announces "Restricted" (Review Focus 1, in the UI); toggle calls the command API; a confirm button runs only after confirming
  - `Markdown.test.tsx`: `<script>` and `<img onerror>` appear as plain text (Review Focus 4)
  - a layout test at 360 px: one column (Review Focus 5)
  - axe
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun the tests, then lint and build. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(console): the actions dashboard"`

---

### Task 8: The admin shell, Home, Devices and Users & permissions

**Files:**
- Create: `console/src/admin/AdminLayout.tsx`, `Home.tsx`, `Devices.tsx`, `Users.tsx`, `Groups.tsx`, `Screens.tsx`, `Access.tsx`, `Tokens.tsx`, `Audit.tsx`, `SignIns.tsx`

**Interfaces:**
- **Admin layout** follows the mockups (`Main.dc.html`, `Users.dc.html`): a left nav of only the sections in `me.sections`, a breadcrumb, a page title and a command bar. List pages follow the framework's "List blade" pattern: search, filter pills, a sortable table, and 50 rows per page.
- **Home:** the tiles `GET /summary` returns, each one linking to a filtered list.
- **Devices:** all devices, by room and unavailable. A side panel renames a device or moves it to a room (`PATCH /entities/{id}`), and rooms are managed in the same page. Restricted stubs show as locked rows with no edit.
- **Users:** create, role, enable or disable, expiry, and "reset to role default". The **last-Admin 409** is shown as its message.
- **Groups:** members.
- **Screens:**
  - **Add:** shows the enrollment link and a **QR code** of it (this closes Plan 2's deferred item), with a 10-minute countdown.
  - **Approve:** shows the fingerprint next to the one the tablet displays, plus a "they match" checkbox.
  - **Revoke:** asks for confirmation.
- **Access:** the spec's table (`Users and permissions › Access`). There's one row per item, with Type, Status (switch), Visibility (Show/Hide/Restrict), "Others see it" (Locked/Not at all, shown only when Restrict is chosen), Network (Anywhere/Local only), and **Assigned to** chips with a picker that has Users, Groups, Roles and Screens tabs. Changes save per row, with an undo toast.
- **Tokens:** create (shown once, with a copy button), list, revoke.
- **Audit log** and **Sign-in log:** tables, with old and new values shown side by side for audit entries.

- [ ] **Step 1: Write failing tests:**
  - `AdminLayout.test.tsx`: the nav shows only your sections
  - `Access.test.tsx`: changing Visibility to Restrict reveals "Others see it"; adding a group chip sends `PUT /items/{id}/assignments` with the right body; keyboard-only operation (Review Focus 5)
  - `Screens.test.tsx`: the QR code renders the enroll URL; approve needs the "they match" box
  - `Users.test.tsx`: the 409 message is shown
  - `Devices.test.tsx`: stubs aren't editable
  - axe on each
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun the tests, then lint and build. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(console): admin home, devices, users and permissions"`

---

### Task 9: Automations, routines, the sentence builder, recipes and the Test Center

**Files:**
- Create: `console/src/admin/Automations.tsx`, `SentenceBuilder.tsx`, `recipes.ts`, `Traces.tsx`, `TestCenter.tsx`, `console/src/editor/YamlEditor.tsx` (Monaco + `monaco-yaml`, schemas fetched from `/api/v1/schemas`)

**Interfaces:**
- **Lists:** automations and routines, with name, enabled, last run outcome, and a "Run" button where allowed.
- **Editor:**
  - It has three views of the same file: **Simple** (the sentence builder, or recipes for a new one), **Advanced** (YAML) and **Runs** (traces).
  - Saving does `PUT /automations/{id}` with the YAML text, after a **diff dialog** (old vs new).
  - A 403 from the save guard is shown as the API's sentence, for example "You can't save this because you don't have access to: cover.garage_door".
- **The sentence builder** covers the simple shape only: one trigger (`state`, `numeric_state`, `time`), at most one condition (`state`/`numeric_state`/`time`), and actions from `notify`, `call`, `sequence` and `script`. It reads: "When **UPS** **switches to battery** for **2 minutes**, if **runtime is under 15 minutes**, then **notify me** and **run Lab safe shutdown**."
  - Each bold part is a picker that shows plain names, never IDs. Device pickers list only devices the user can control.
  - `toYaml(sentence)` and `fromYaml(yaml)` convert between the two. `fromYaml` returns `null` for anything outside that shape, and the Simple tab then says "This automation uses features the Simple view can't show; use Advanced." **Saving from Simple never drops YAML the user wrote:** it's disabled when `fromYaml` returned `null`.
- **Recipes** (`recipes.ts`), with the framework's list cut to Phase 1's triggers:
  1. lights on at a time and off at another
  2. notify me when the washer finishes (power below N watts for 5 minutes)
  3. alert me and run a routine when the UPS is on battery
  4. run a script on a schedule

  "Everything off when the last person leaves" and "door opens while I'm away" need presence, which comes later, so they're listed as "coming later". Each recipe is a set of blanks and builds the same YAML the sentence builder would.
- **Traces:** each step with its path, its detail and the result (a "what if" result has its own chip). Restricted traces show "restricted" as the API returns it.
- **Test Center** (needs `feature:test_center`):
  - pick an automation or routine, or "Test my unsaved changes" from the editor
  - set the trigger and simulated device values (pickers prefilled from the automation's references)
  - optionally "start at step…" (a tree of the steps)
  - set script samples (prefilled from headers by the API)
  - run, then show the trace with every "What if:" line, and the summary line in a highlighted box

- [ ] **Step 1: Write failing tests:**
  - `SentenceBuilder.test.ts(x)`: `toYaml(fromYaml(x)) == x`, normalised, for the UPS example and each recipe; `fromYaml` gives `null` for a `choose`; saving is disabled then; the pickers show names, not IDs
  - `recipes.test.ts`: each recipe's YAML validates against `schemas/automation.json`, loaded from the repo
  - `YamlEditor.test.tsx`: text containing `</script>` stays text (Review Focus 4)
  - `TestCenter.test.tsx`: posts the right body and renders the summary
  - axe on each
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Load `frontend-design` first for the editor's look.
- [ ] **Step 4:** Rerun the tests, then lint and build. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(console): automations, sentence builder, recipes and test center"`

---

### Task 10: Scripts, dashboards and System pages

**Files:**
- Create: `console/src/admin/Scripts.tsx`, `Dashboards.tsx`, `Networks.tsx`, `Certificate.tsx`, `ConfigErrors.tsx`

**Interfaces:**
- **Scripts** follows `Scripts.dc.html`:
  - a list with a language badge and last result
  - an editor (Monaco with PowerShell, Python and shell highlighting) with a header summary
  - a **Test run** form built from the header's params, which shows the output and result, and the last 20 log lines on failure
  - the run log
  - a secrets warning when the header lists secrets ("Only an Admin can save this")
- **Dashboards:** a list (open / edit). The editor is YAML, with a live preview using the same renderer as Task 7, fed by a draft view. **Preview reuses `GET /dashboards/{slug}/view` after saving**, so there's no draft rendering endpoint. `shortcut: preview shows the saved version; add a draft-view endpoint if editing feels slow`. An **Access** link jumps to the item's row in the Access table.
- **System:**
  - **Networks:** local ranges and trusted proxies, with the API's 422 text inline.
  - **Certificate:** the fingerprint, expiry and self-signed flag, plus how to use your own.
  - **Config errors:** `GET /config/errors`, as a list with file:line links that open the right editor.
  - **General** (location, time zone, units) waits for the sun triggers that need it. `shortcut: no General page in Phase 1; time zone comes from the host`.

- [ ] **Step 1: Write failing tests:**
  - `Scripts.test.tsx`: the param form from a header; a failure shows the tail
  - `Dashboards.test.tsx`: save then preview; the Access link
  - `Networks.test.tsx`: the 422 shows inline
  - `ConfigErrors.test.tsx`: links
  - axe on each
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun the tests, then lint and build. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(console): scripts, dashboards and system pages"`

---

### Task 11: A real walk-through, and docs

**Files:**
- Create: `docs/console.md`
- Modify: `README.md` (one link)

- [ ] **Step 1: Build and serve.** Run `pnpm --dir console build`, then start `python -m cave serve` with fresh `--data`/`--config` folders in the scratchpad, plus a `config/` holding the Plan 4 fixtures and a kids/garage dashboard. Open it in the built-in browser pane. The pane refuses self-signed HTTPS (Plan 2), so for this check only, run the console through Vite's dev server (`pnpm --dir console dev`, proxying `/api` to a local plain-HTTP uvicorn on `127.0.0.1`), as Plan 2's smoke test did.
- [ ] **Step 2: Walk through and screenshot each step:**
  1. setup with the printed code
  2. enrol TOTP (compute codes from the URI with `pyotp` in the shell)
  3. create a household user
  4. assign the kids dashboard
  5. sign in as them: no admin link, the locked garage tile, the restricted markdown
  6. back as the Admin: run the UPS example in the Test Center
  7. the Access table, keyboard only
  8. 360 px and high contrast

  Write down anything broken, then fix it TDD-style, with a failing component or API test first.
- [ ] **Step 3:** Write `docs/console.md`:
  - first-run setup, and where the code appears
  - signing in, and the authenticator app
  - dashboards and locked tiles
  - each console section, one paragraph each
  - the sentence builder's limits
  - recipes
  - the Test Center
  - keyboard shortcuts, if any
- [ ] **Step 4:** Run the full Python suite, then `pnpm --dir console lint && pnpm --dir console test && pnpm --dir console build`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "docs(console): console guide and walk-through fixes"`

---

## Plan 6 done when

- Python CI and console CI are both green.
- A new CAVE can be set up from a browser with the one-time code: an owner with an authenticator app, and nothing else on the LAN can claim it.
- A household member sees only their dashboards, locked tiles for anything restricted, and no admin console. Everything is decided by the server.
- An Admin can manage devices, rooms, users, groups, screens (with the QR code), access, tokens, automations (with the sentence builder, recipes and the Test Center), scripts, dashboards, networks and the certificate, and read the audit and sign-in logs.
- The walk-through in Task 11 passed in a real browser, including keyboard-only use, 360 px wide and high contrast.
- Left for Plan 7: building the console in the image, and the Compose stack.
