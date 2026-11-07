# Dashboard Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dashboard in the console by adding, moving, restyling and grouping tiles, with YAML still available on the same page.

**Architecture:** The YAML file stays the only stored form. The console holds one draft as YAML text; pure functions in `model.ts` parse it to a plain object, change it and write it back, so fields the builder doesn't know survive. Three React panels sit on those functions, and the existing `PUT /dashboards/{slug}` saves the result.

**Tech Stack:** Python 3.13, Pydantic v2, FastAPI; React 19, Fluent UI v9, TanStack Query, the `yaml` package, native HTML drag and drop, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-06-dashboard-builder-design.md`

## Global Constraints

- No new dependencies. No new tables.
- Every access check goes through `cave.access.evaluate` (or `can_control` / `assert_can_save`).
- Never call real devices or the network in tests. Never log secrets.
- Everything works without dragging: Add buttons and Move controls are required.
- The builder never sends a device command or starts a run.
- Sizes: Small `w3 h1`, Wide `w6 h1`, Tall `w3 h2`, Large `w6 h2`. Anything else shows as Custom and is kept.
- Colours: `blue`, `green`, `amber`, `red`, `purple`; no value means Default.
- Icons: `lightbulb`, `plug`, `power`, `wind`, `fire`, `temperature`, `drop`, `sun`, `snow`, `door`, `lock`, `shield`, `camera`, `speaker`, `tv`, `home`, `bed`, `clock`, `play`, `battery`.
- Console words: "routine" for a sequence, sentence case, no em dashes in copy.
- Commits: Conventional Commits, `git commit -s`, ending with the session's Co-Authored-By line.
- Core checks, from `core/`: `../.venv/Scripts/python -m pytest -q -p no:cacheprovider`, `-m ruff check .`, `-m mypy --strict cave`.
- Console checks, from `console/`, after `export PATH="/c/Program Files/nodejs:$PATH"`: `npx --no-install vitest run`, `npx --no-install tsc -b`, `npx --no-install eslint .`.

## Review Focus

1. A hand-written card with `severity`, a custom size or a field the builder has no control for, then one visual edit: the field is still there. Task 3 test.
2. Clicking a toggle tile or run button on the canvas selects it and sends nothing. Task 4 test.
3. Removing a tile before the selected one, or removing the selected one: selection never lands on the wrong tile. Task 3 test.
4. A dashboard with no `views` key: Add group still works and creates a `main` view. Task 3 test.
5. An operator who gets 403 from `/scripts` or `/automations`: the rest of the left panel still works. Task 4 test.
6. A script file name with dots: `script.backup-photos.sh` runs that file, not `backup-photos`. `split(".", 2)` in `Button.tsx` truncates it today. Task 2 test.

## Rulings on the spec

- `BrowserRouter` doesn't support `useBlocker`. The unsaved-changes guard is `beforeunload` only, with a `shortcut:` comment. Moving to a data router is out of scope.
- `ajv` is a dev dependency, so "fits the schema" in the console is a shape check (`parseDraft`). Full validation stays on Save.
- `ConfigStore.guard` keeps checking the `script:<file>` item only. It's stricter than the run route and only affects non-Admins.

---

### Task 1: Core: card fields and script buttons

**Files:**
- Modify: `core/cave/config/models.py:287-331`, `core/cave/config/refs.py:99-104`, `core/cave/api/views.py:69-92`, `core/cave/api/scripts.py:50-60`, `schemas/dashboard.json`
- Test: `core/tests/test_dashboard_cards.py` (new)

**Interfaces:**
- Produces: YAML fields `icon`, `color` on every card; `label` on `tile`, `gauge`, `entities`; `action: script.<file>` on `button`. `GET /scripts` rows gain `"runnable": bool`, true when no param is required.

- [ ] **Step 1: Write the failing tests**

Use the helpers in `core/tests/test_config_api.py` (`put_file`) and `tests.conftest` (`lan_client`, `sign_in`).

```python
def test_cards_take_a_label_icon_and_colour(): ...   # parse() accepts label: Lamp, icon: wind, color: blue
def test_unknown_icon_or_colour_is_refused(): ...    # icon: rocket, color: pink raise ConfigError
def test_view_passes_the_new_fields_through(): ...   # view card has label, icon, color
def test_a_script_button_needs_a_valid_file(): ...   # script.backup-photos.sh ok; script.../x.sh refused
def test_script_button_is_listed_and_allowed_for_who_can_run_it(): ...  # allowed True via item, and via section:scripts
def test_script_button_is_hidden_when_not_listed(): ...  # same as automation buttons: card absent
def test_saving_a_script_button_you_cant_run_is_refused(): ...  # non-Admin gets the existing AccessDenied message
def test_script_list_says_which_can_run_from_a_button(): ...  # required param -> runnable False, else True
```

- [ ] **Step 2: Run them**

Run: `../.venv/Scripts/python -m pytest tests/test_dashboard_cards.py -q -p no:cacheprovider`
Expected: FAIL, unknown fields are refused by `_Strict`.

- [ ] **Step 3: Implement**

- `models.py`: `CardIcon` and `CardColor` as `Literal`s with the Global Constraints values. `_Card` gains `icon: CardIcon | None = None`, `color: CardColor | None = None`. `TileCard`, `GaugeCard`, `EntitiesCard` gain `label: str | None = Field(default=None, max_length=100)`. Widen the `ButtonCard.action` pattern with a `script\.` branch whose file part matches `FILE_NAME` in `cave/scripts/header.py`.
- `refs.py`: `script` actions go in `scripts`.
- `views.py`: in `_card`, a `script` action is allowed if `evaluate` allows `script:<file>` or `section:scripts`, and listed if the item is listed or the section is allowed.
- `scripts.py`: add `runnable`. Check how `Param` marks required in `cave/scripts/header.py`.

- [ ] **Step 4: Regenerate schemas and run all core checks**

Run: `../.venv/Scripts/python -m cave schemas`, then the three core checks.
Expected: all pass, including `test_schemas_committed_match_generated`.

- [ ] **Step 5: Commit**: `feat(core): add tile label, icon and colour, and script buttons`

---

### Task 2: Cards show the new look

**Files:**
- Create: `console/src/cards/look.tsx`, `console/src/cards/look.test.tsx`
- Modify: `console/src/api/types.ts`, `console/src/cards/Tile.tsx`, `Gauge.tsx`, `Button.tsx`, `entity.ts`, `console/src/admin/Devices.tsx`, `console/src/pages/Dashboard.tsx`, `console/src/app/app.css`

**Interfaces:**
- Consumes: Task 1 fields.
- Produces:
  - `ICONS: Record<string, FluentIcon>`, `COLORS: readonly string[]`, `CardIcon({ name }: { name?: string | null })` in `look.tsx`.
  - `SWITCHABLE: Set<string>` moved to `cards/entity.ts`, used by `Devices.tsx`.
  - `CardBody` exported from `pages/Dashboard.tsx`.
  - `Card` types gain `icon?`, `color?`, and `label?` where Task 1 added it.

Icon mapping: `lightbulb` LightbulbRegular, `plug` PlugConnectedRegular, `power` PowerRegular, `wind` WeatherSquallsRegular, `fire` FireRegular, `temperature` TemperatureRegular, `drop` DropRegular, `sun` WeatherSunnyRegular, `snow` WeatherSnowflakeRegular, `door` DoorRegular, `lock` LockClosedRegular, `shield` ShieldRegular, `camera` CameraRegular, `speaker` Speaker2Regular, `tv` TvRegular, `home` HomeRegular, `bed` BedRegular, `clock` ClockRegular, `play` PlayRegular, `battery` BatteryChargeRegular.

- [ ] **Step 1: Write the failing tests**

```tsx
it("offers exactly the icons and colours the core accepts") // keys of ICONS and COLORS equal the enums in schemas/dashboard.json
it("shows a tile's label instead of the device name")
it("shows the card's icon")
it("runs a script button by its whole file name") // POST /scripts/backup-photos.sh/run for action script.backup-photos.sh
it("every colour keeps readable text in light and dark") // contrast() from app/theme >= 4.5 for each tint pair
```

- [ ] **Step 2: Run them**: `npx --no-install vitest run src/cards/look.test.tsx`. Expected: FAIL, no `look.tsx`.

- [ ] **Step 3: Implement**

- `Tile` takes `label?: string | null` and `icon?: string | null`. `Gauge` and `Entities` read them from the card.
- `Button.tsx`: split the action on the first dot only, and map `script` to `/scripts/{file}/run`.
- `Dashboard.tsx`: the `.card` wrapper gets class `tint-${c.color}` when set.
- `app.css`: each `.tint-*` overrides `--raised`, `--accent-tint`, `--accent` and `--accent-ink` on the wrapper, so off is pale and on is stronger, and no card needs its own rule. Define the tint values per theme in the three existing token blocks. High contrast keeps system colours.
- Export the tint hex pairs from `look.tsx` if the contrast test needs them; the CSS and that list must be one source or be checked against each other in the test.

- [ ] **Step 4: Run console checks**. Expected: all pass.

- [ ] **Step 5: Commit**: `feat(console): show tile labels, icons and colours`

---

### Task 3: The draft model

**Files:**
- Create: `console/src/admin/builder/model.ts`, `console/src/admin/builder/model.test.ts`

**Interfaces:**
- Consumes: `SWITCHABLE`, `FullEntity`, `EntityView`, `Card`.
- Produces, all pure, all returning a new `Draft` and never changing the input:

```ts
export type DraftCard = { type: string; w?: number; h?: number; [k: string]: unknown };
export interface DraftGroup { title: string; cards?: DraftCard[]; [k: string]: unknown }
export interface DraftView { id: string; title: string; sections?: DraftGroup[]; [k: string]: unknown }
export interface Draft { dashboard: { title: string; views?: DraftView[]; [k: string]: unknown } }
export interface Spot { view: number; group: number; card: number }
export type Source =
  | { kind: "device" | "sensor"; entity: FullEntity }
  | { kind: "automation" | "routine" | "script"; id: string; name: string }
  | { kind: "note" | "list" };

export function parseDraft(text: string): { draft: Draft } | { reason: string };
export function writeDraft(draft: Draft): string;
export function hasComments(text: string): boolean;
export function cardFor(source: Source): DraftCard;
export function addCard(d: Draft, view: number, group: number, card: DraftCard): Draft;
export function moveCard(d: Draft, from: Spot, to: Spot): Draft;
export function removeCard(d: Draft, at: Spot): Draft;
export function updateCard(d: Draft, at: Spot, change: Record<string, unknown>): Draft;
export function addGroup(d: Draft, view: number, title: string): Draft;
export function renameGroup(d: Draft, view: number, group: number, title: string): Draft;
export function moveGroup(d: Draft, view: number, from: number, to: number): Draft;
export function removeGroup(d: Draft, view: number, group: number): Draft;
export function afterRemove(selected: Spot | null, removed: Spot): Spot | null;
export function sizeOf(card: DraftCard): "small" | "wide" | "tall" | "large" | "custom";
export function viewCard(card: DraftCard, states: EntityView[]): Card;
```

Rules the tests pin:
- `cardFor`: switchable device gives `tile` with `tap_action: toggle`; other devices and sensors give `tap_action: none`; automation gives `button` with `action: automation.<id>`, routine gives `sequence.<id>`, script gives `script.<file>` with `confirm: true`; note gives `markdown` with `content: ""`; list gives `entities` with `entities: []`. All `w: 3, h: 1`.
- `updateCard` deletes a key when its value is `""`, `null` or `undefined`, so a cleared label doesn't write `label: ""`.
- `addGroup` creates `{ id: "main", title: "Main" }` when there are no views.
- `viewCard` fills `entity` from `states`, or `{ entity_id, name: entity_id, area_id: null, missing: true }`. Tiles show locked when restricted. Markdown `text` is the raw `content`. Buttons are `allowed: true`.

- [ ] **Step 1: Write the failing tests**

```ts
it("keeps fields it has no control for") // severity, custom w/h and an unknown key survive parse, updateCard, write
it("explains YAML it can't use") // bad YAML; no dashboard key; a card with an unknown type -> { reason }
it("adds a view when the dashboard has none") // "dashboard:\n  title: Gate\n" then addGroup
it("moves a tile within a group and between groups")
it("moving to the same place changes nothing")
it("removing a group removes its tiles")
it("a cleared label leaves no label key")
it("finds real comments but not a # inside a value") // color "a#b" false; "# note" true
it("keeps the selection on the right tile after a removal") // afterRemove: earlier tile shifts, same tile null, later unchanged, other group unchanged
it("gives each kind of item its default tile") // every cardFor rule above
it("names sizes, and calls anything else custom")
```

- [ ] **Step 2: Run them**: `npx --no-install vitest run src/admin/builder/model.test.ts`. Expected: FAIL, no module.

- [ ] **Step 3: Implement** in `model.ts`. Use `parse` and `stringify` from `yaml`, and `parseDocument` with `visit` for `hasComments`.

- [ ] **Step 4: Run console checks**. Expected: all pass.

- [ ] **Step 5: Commit**: `feat(console): add the dashboard builder's draft model`

---

### Task 4: The three panels

**Files:**
- Create: `console/src/admin/builder/Builder.tsx`, `Palette.tsx`, `Canvas.tsx`, `Settings.tsx`, `console/src/admin/builder/builder.test.tsx`
- Modify: `console/src/app/app.css`

**Interfaces:**
- Consumes: everything in Task 3, `CardBody`, `ICONS`, `COLORS`.
- Produces: `Builder({ draft, onChange }: { draft: Draft; onChange: (d: Draft) => void })`.

Behaviour:
- `Palette` queries `/states`, `/automations`, `/sequences` and `/scripts`, each separately, with `retry: false`. A failed list hides its heading. Shows only unrestricted entities, `allowed` items and `runnable` scripts. Sensors are capabilities `sensor`, `binary_sensor`, `device_tracker` and `weather`. Rows are `draggable`, with an Add button named `Add <name>`.
- `Canvas` shows tabs when `views.length > 1`. Each tile is a wrapper holding a `Select <label>` button, the card from `CardBody` inside an `inert` div, and a `Remove <label>` button. Tiles and groups are both draggable. Drag data is the `Spot`, group index or `Source` as JSON under a custom type. Ignore a drop with no data.
- `Settings` has the fields in the spec's table. Shows as: Toggle only if `SWITCHABLE`, Gauge only if the state is numeric. Changing to Gauge sets `type: gauge` and removes `tap_action`; back sets `type: tile`. Move earlier, Move later and Move to group call `moveCard`. A group selection shows its name and Remove, plus Move earlier and Move later.
- A `role="status"` region announces each move, such as "Right fan moved to Office."
- Layout: `.builder` grid of `260px minmax(0, 1fr) 280px`.

- [ ] **Step 1: Write the failing tests**

```tsx
it("adds a device to the selected group with its Add button")
it("adds to the last group when none is selected")
it("hides what you can't use") // restricted entity, allowed: false, runnable: false absent
it("still works when a list is refused") // GET /scripts 403: no Scripts heading, devices still listed
it("searches across every list")
it("never switches or runs anything from the canvas") // click toggle tile and run button; no POST in calls
it("moves a tile with the Move controls and announces it")
it("moves a tile to another group")
it("moves a tile by dragging") // fireEvent dragStart + drop with a stub dataTransfer
it("removes a tile and clears its settings")
it("renames, moves and removes a group")
it("reorders groups by dragging")
it("changes label, icon, colour and size")
it("shows a size from YAML as Custom and keeps it")
it("offers Toggle only for what switches, and Gauge only for numbers")
it("keeps a restricted tile locked but movable")
it("passes an accessibility check") // expectAccessible
```

- [ ] **Step 2: Run them**: `npx --no-install vitest run src/admin/builder/builder.test.tsx`. Expected: FAIL, no module.

- [ ] **Step 3: Implement** the four components. `Builder` holds the selection and uses `afterRemove`.

- [ ] **Step 4: Run console checks**. Expected: all pass.

- [ ] **Step 5: Commit**: `feat(console): add the three-panel dashboard builder`

---

### Task 5: Visual and YAML on the editor page

**Files:**
- Modify: `console/src/admin/Dashboards.tsx`, `console/src/admin/dashboards.test.tsx`

**Interfaces:**
- Consumes: `Builder`, `parseDraft`, `writeDraft`, `hasComments`.

Behaviour:
- One draft string, `text ?? doc.data.yaml`. Mode starts as Visual when `parseDraft` succeeds, otherwise YAML.
- The top bar gets a Visual/YAML toggle, Save, Discard (enabled only with unsaved changes), Access and Delete.
- Visual is disabled when `parseDraft` gives a reason, and the reason shows beside the switch.
- The first visual change on text where `hasComments` is true opens a dialog: "Remove the comments in this YAML?" with Keep editing in YAML and Remove comments. Nothing changes until Remove comments is chosen.
- YAML mode keeps the existing editor and preview. Save stays on the page and clears the draft.
- `beforeunload` guard while there are unsaved changes, with `// shortcut: BrowserRouter has no in-app blocker, move to a data router to warn between pages`.
- `starter(name)` becomes one group titled "Main" with no cards, so a new dashboard opens as an empty builder.

- [ ] **Step 1: Write the failing tests**

```tsx
it("opens in Visual, and a new dashboard is an empty builder")
it("carries unsaved changes from Visual to YAML and back")
it("disables Visual with the reason when the YAML can't be used")
it("opens broken YAML straight in YAML")
it("warns before a visual change removes comments") // both answers
it("saves the draft through the normal route") // PUT /dashboards/gate with the written YAML
it("shows a save refusal and keeps the draft") // PUT 403
it("Discard goes back to the saved version")
it("asks before closing with unsaved changes") // beforeunload default prevented only when dirty
```

Update the existing create test if `starter` wording changes.

- [ ] **Step 2: Run them**: `npx --no-install vitest run src/admin/dashboards.test.tsx`. Expected: new tests FAIL.

- [ ] **Step 3: Implement** in `DashboardEditor`. Keep `slugOf` and the delete flow.

- [ ] **Step 4: Run console checks**. Expected: all pass.

- [ ] **Step 5: Commit**: `feat(console): edit dashboards visually or in YAML`

---

### Task 6: Small screens, docs and real checks

**Files:**
- Modify: `console/src/admin/builder/Builder.tsx`, `builder.test.tsx`, `console/src/app/app.css`, `console/src/preview/main.tsx`, `console/src/preview/fixtures.ts`, `README.md`
- Create: `docs/dashboards.md`

- [ ] **Step 1: Write the failing test**

```tsx
it("folds the side panels into drawers on a narrow screen") // setNarrow(true): Add and Settings buttons open drawers; adding still works
```

- [ ] **Step 2: Run it**. Expected: FAIL.

- [ ] **Step 3: Implement**. Use `useNarrow` and `OverlayDrawer`, as `AddDevice` does. Add `/dashboards/home` YAML to the preview fixtures, and a `runnable` field to its scripts. Write `docs/dashboards.md` in plain steps: building, tile settings, YAML and comments, what needs Scripts access. Link it from the README.

- [ ] **Step 4: Run all core and console checks**. Expected: all pass.

- [ ] **Step 5: Check in the preview**

`preview_start` with `console-dev`, then open `/preview.html?path=/admin/dashboards/home` in light and dark, and at phone width. Drag a tile by hand, since jsdom can't prove a real drag. Check no console errors.

- [ ] **Step 6: Commit and check on the VM**

Commit: `feat(console): fold the builder panels on small screens and add docs`. Push the branch, then fetch it on the test VM from `https://github.com/justwork500/cave.git` and run `docker compose build cave && docker compose up -d cave`. Don't switch any device yourself: the user tests on real hardware.
