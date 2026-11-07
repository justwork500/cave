# Dashboard builder design

## Why

Today a dashboard can only be built by hand-writing YAML, and a device ID has to be typed exactly. That's the opposite of what CAVE promises a household. Anyone with access to Dashboards should be able to get a working dashboard by dragging in what they have, then make it look the way they want. YAML stays for anyone who wants more control.

## Goals

- A three-panel visual builder on the dashboard editor page.
- Add, move and remove tiles, and add, rename, reorder and remove groups.
- Add devices, sensors, automations, routines and scripts, plus text notes.
- Per-tile label, icon, colour, size and display type.
- A Visual/YAML switch on the same page, both editing the same dashboard.
- New dashboards open in the builder.

## Non-goals

- A free-form canvas with pixel positioning. Tiles flow, so phones keep working.
- Creating or renaming dashboard tabs (YAML `views`). Existing tabs can be edited in the builder.
- Undo history. Nothing changes until Save, and Discard goes back to the saved version.
- Asking for confirmation before a toggle tile switches a device.
- Live preview of templates inside text notes.
- Custom images or free colour picking.

## Must not happen

- A dashboard written in YAML loses settings just by being opened and saved in the builder, apart from the comments warning below.
- A person adds something to a dashboard that they can't use. Existing access checks stay the only gate.
- Colours that become unreadable in dark or high-contrast themes.
- Building depends on dragging. Everything must also work by keyboard and touch.

## The screen

Route: the existing `/admin/dashboards/:slug`. The top bar has the dashboard name, the Visual/YAML switch, Save, Discard, Access and Delete.

- **Left, Add to dashboard:** a search box, then Devices, Sensors, Automations, Routines, Scripts and Other (text note, list tile). Each row can be dragged to the canvas or added with its Add button, which puts it in the selected group, or the last group if none is selected.
- **Middle, the dashboard:** tabs if there's more than one view, then groups with their tiles. Tiles drag within and between groups, and groups drag to reorder. Tiles use the real card components with live state, but tapping selects rather than switches. Each tile has a remove button. An Add group button sits at the end.
- **Right, Tile settings:** the selected tile's settings, or the selected group's name and Remove. With nothing selected, a short hint. It also holds Move earlier, Move later and a Move to group picker, which are the keyboard and touch route for moving.

Below about 900px wide, the left and right panels become drawers opened by Add and Settings buttons. The Add buttons and Move controls mean this works without dragging.

## Tile settings

| Setting | Applies to | Values |
| --- | --- | --- |
| Label | all except text note | Free text. Blank uses the device's own name. Changes this tile only. |
| Shows as | devices and sensors | Toggle, Status only, Gauge. Toggle is offered only for devices that switch. Gauge is offered only for numeric sensors. |
| Icon | all except text note | None or one from a fixed set of about 20. |
| Colour | all except text note | Default, Blue, Green, Amber, Red, Purple. Each has light, dark and high-contrast values. |
| Size | all | Small (3 by 1), Wide (6 by 1), Tall (3 by 2), Large (6 by 2). Other sizes from YAML show as Custom and are kept unless changed. |
| Min and max | gauge | Numbers. |
| Items | list tile | Add, remove and reorder. |
| Ask before running | run buttons | On or off. |
| Text | text note | Text box. |

Defaults when added: switches and lights are a Toggle, sensors are Status only, automations and routines are a run button, and scripts are a run button with Ask before running on. A list tile is made by adding an item from the Other section, then choosing what goes in it.

## Data

The YAML file stays the only stored form. No new tables and no second format.

- `_Card` gains optional `icon` and `color`, validated against the fixed sets. `TileCard`, `GaugeCard` and `EntitiesCard` gain optional `label`. `ButtonCard` keeps `name`.
- `ButtonCard.action` also accepts `script.<file>`.
- `schemas/dashboard.json` is regenerated from the models.
- `/dashboards/{slug}/view` passes the new fields through. The dashboard page and cards render them, so the saved result matches the builder.

### Scripts on dashboards

- `_card` checks access through `evaluate` using the same rule as the run route: the `script:<file>` item or `section:scripts`. It hides or locks the button the way it does for automations and routines.
- `refs()` and the save check treat a script button like the other run buttons.
- The console posts to the existing `/scripts/{file}/run`.
- Only scripts with no required parameters are offered in the left panel, because a button has nowhere to enter them. `GET /scripts` gains a field saying so.

## Visual and YAML together

One draft, held as YAML text. Visual parses it with the `yaml` package the console already has, and each visual change writes it back.

- Switching to YAML shows the draft, including unsaved changes.
- If the YAML doesn't parse or doesn't fit the schema, Visual is disabled with the reason, and the YAML is left untouched.
- Fields the builder has no control for are carried through unchanged.
- If the saved YAML has comments, the first visual change warns that they'll be removed and offers to stay in YAML.
- Save uses the existing `PUT /dashboards/{slug}`, so its validation and access checks apply. Errors show in the existing error bar.
- Closing or reloading the tab with unsaved changes asks first, through `beforeunload`. CAVE has no guard for moving between pages inside the console yet. Add one if the router supports it, otherwise note it as a known limit.

## Access

No new access rules. The left panel lists only what the person can use: entities from `/states` that aren't restricted, and allowed automations, routines and scripts. Those lists need the matching console section, so someone without Scripts access simply doesn't see the Scripts heading. Restricted tiles already in a dashboard stay in place and show as locked, and can be moved or removed. The server remains the real check.

## Accessibility

Native drag and drop is used, so no new dependency. It doesn't work by keyboard or on most touch screens, so the Add buttons and Move controls are required rather than extras. Moves are announced through a live region. Tests include axe checks on the builder.

## Tests

- Core: new fields accepted and bad values refused, `script.` actions, script access in `_card`, save refused for a script the person can't use, schema file up to date.
- Console: add by button, move by controls, remove, rename a group, edit label, icon, colour and size, YAML to Visual and back keeps unknown fields, invalid YAML disables Visual, comments warning, restricted tile stays locked, dashboard renders the new fields in both themes.
- Drag behaviour is tested through the same move function the controls use, then checked once by hand in a browser.

## Left to the builder

- The exact icon set, as long as it maps to Fluent icons already in use.
- Exact colour values, as long as they pass contrast checks.
- Component and file structure under `console/src/admin/`.
