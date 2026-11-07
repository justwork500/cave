# Building dashboards

Open **Dashboards**, type a name and choose **Create dashboard**, or choose **Edit** next to one you already have. It opens in the visual builder. Nothing changes until you choose **Save**, and **Discard** goes back to the saved version.

## The three panels

- **Add to dashboard**, on the left, lists what you can use: devices, sensors, automations, routines and scripts, plus text notes and list tiles. Drag an item onto the dashboard, or use its Add button to put it in the selected group.
- **The dashboard**, in the middle, shows your groups and tiles. Drag tiles within or between groups, and drag a group by its name to reorder it. Tiles only select here: nothing switches or runs until the dashboard is saved and opened.
- **Settings**, on the right, change whatever you've selected. **Move earlier**, **Move later** and **Move to group** do the same as dragging, by keyboard or touch.

On a tablet or phone the side panels open from the **Add** and **Settings** buttons.

## Tile settings

- **Label:** a name for this tile only. The device keeps its own name everywhere else.
- **Shows as:** Toggle for things that switch, Status only, or Gauge for numbers. A list tile shows several items together.
- **Icon** and **Colour:** chosen from fixed sets, so they stay readable in light and dark.
- **Size:** Small, Wide, Tall or Large. A size set in YAML shows as Custom and stays until you change it.
- **Ask before running:** a run button asks first. It's on by default for scripts.

Only scripts that need no input can go on a dashboard, because a button has nowhere to ask for it.

## Using YAML

**YAML**, at the top, shows the same dashboard as text, including unsaved changes. If the text can't be drawn, **Visual** is turned off and says why.

The builder keeps every setting it doesn't show, but it rewrites the file, so comments are removed. It asks before the first change that would do this.

## What you'll see

The Add list shows only what you can use, and needs the matching section: without access to Scripts, there's no Scripts heading. A tile you can't use stays locked, and you can still move or remove it.

Closing or reloading the tab with unsaved changes asks first. Moving to another page in the console doesn't, so save before you leave.
