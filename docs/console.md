# The CAVE console

The console is the web app CAVE serves at its own address (for example `https://cave.local:8443`). It has two parts:

- **Dashboards**: what everyone in the house uses.
- **The admin console**: only for people who have at least one console section.

Every decision about what you can see or use is made by the server. The console only shows what the server sends.

## First-run setup

A new CAVE has no users. When it starts, it prints a one-time setup code in its console, like this:

```
CAVE isn't set up yet. Open it in a browser and use this one-time setup code: 7KQ2-M9XD-…
```

Open CAVE in a browser. It goes straight to **Set up CAVE**. Setup has four steps:

1. Enter the setup code. Anyone else on your network who doesn't have the code can't claim CAVE.
2. Create the owner account. The password needs at least 12 characters.
3. Scan the QR code with an authenticator app, or type in the key shown under it. Then enter a code from the app.
4. Save the ten recovery codes, tick "I've saved these codes somewhere safe", and go to CAVE.

Each recovery code signs you in once if you lose your phone. The codes are never shown again.

A new code is printed on every start until the owner exists.

## Signing in

Sign in with your username and password. If your account needs an authenticator app, CAVE asks for a code next. A recovery code works in the same box. If your account needs an authenticator app but you haven't set one up yet, CAVE walks you through steps 3 and 4 above.

To change your password, theme (light, dark or high contrast) or the dashboard that opens first, go to **Profile and theme** in the menu under your name. Your theme and first dashboard are saved in that browser only.

## Dashboards and locked tiles

A dashboard shows tiles, gauges, lists, buttons and text. Tap a tile to switch it on or off. Changes from anywhere show up live.

**Anything put on a dashboard can be seen and used by everyone who can open that dashboard.** For example, if the Kids dashboard has a garage door tile, anyone who can open Kids can open the garage. Restrict the dashboard (in **Access**) to keep it to the right people or screens.

Something you can't use shows as **locked**: a striped tile with a lock and the word "Restricted". You can see that it exists, but not its state or what it can do. A button you can't use is greyed out with a lock. On a phone, every card goes into one column.

## The admin console

The **Admin console** link only appears if you have a console section. The left-hand list shows only your sections. If you type the address of a page you can't use, you see "You don't have access to this", and the server refuses the request anyway.

- **Home** shows what needs attention: MQTT status, devices not responding, automation failures in the last day, and screens waiting for approval. Each one opens the list that explains it.
- **Devices** lists every device with its room and state. Use **Edit** to rename a device or move it to a room. Rooms are added and deleted at the bottom of the page. A device you can't control shows as a locked row and can't be edited.
- **Users** creates people and changes their role, turns accounts on or off, and sets an expiry date. CAVE won't let you disable or demote the last Admin, and says so.
- **Groups** holds sets of people, so you can share something with a group in one step.
- **Screens** adds wall tablets. **Add screen** shows an enrollment link and its QR code, valid for 10 minutes. Open it on the tablet. Approve the screen only when its fingerprint matches the one the tablet shows: tick "They match" to approve. **Revoke** signs a screen out for good.
- **Access** has one row for each dashboard, console section, action and feature:
  - **Status** turns it on or off for everyone.
  - **Visibility** is Show, Hide or Restrict.
  - With Restrict, **Others see it** chooses whether everyone else sees it locked or not at all.
  - **Network** chooses Anywhere or Local network only.
  - **Assign** restricts the row to users, groups, roles or screens.

  Each change saves on its own, with an **Undo**. Everything here works from the keyboard alone.
- **API tokens** creates tokens for other programs. A token is shown once: copy it then.
- **Automations** lists automations and routines, with their last run and a **Run** button.
- **Scripts** lists scripts by language. A script's page shows its settings, an editor and a **Test run** form built from its parameters. If a run fails, you see the last lines it printed. Scripts that use secrets can only be saved by an Admin.
- **Dashboards** opens or edits each dashboard as YAML. **Save and preview** saves it and shows the saved version. The **Access** link jumps to its row in the Access table.
- **System** sets the local network ranges and trusted proxies, and shows the certificate's fingerprint and expiry. It also lists config files that didn't load, each linked to its editor.
- **Audit log** shows every change, with the values before and after. **Sign-in log** shows every sign-in attempt.

## Editing automations

An automation's page has four tabs:

- **Simple**: the sentence builder.
- **Advanced**: the YAML editor, with hints from CAVE's schemas.
- **Runs**: past runs, step by step.
- **Test**: the Test Center, on your unsaved changes.

**Save** first shows what will change, line by line. If you can't save because the automation uses devices you don't control, CAVE says which ones.

### The sentence builder's limits

The Simple tab reads like a sentence: "When **UPS on battery** switches to **on** for **2m**, only if **UPS runtime** is below **15**, then **notify me** and **run Lab safe shutdown**." Each bold part is a choice shown by name. Device choices list only devices you can control.

It covers only this shape:

- **One trigger:** a device changes state, a reading crosses a value, or a set time.
- **At most one condition:** a device state, a reading above or below a value, or between two times.
- **Actions:** notify, control a device, run a routine, or run a script.

Anything else is edited in Advanced. That includes several triggers, `choose`, `repeat`, delays and templates in conditions. In those cases, the Simple tab says "This automation uses features the Simple view can't show; use Advanced", and you can't save from it. The same happens if the file has comments, because rebuilding it would drop them. Saving from Simple never loses YAML you wrote.

### Recipes

A new automation can start from a recipe. Fill in the blanks, and CAVE creates it:

- **Lights on at one time and off at another.** This creates two automations, one for on and one for off.
- **Tell me when the washer finishes.** Power below a number of watts for 5 minutes.
- **Alert me and run a routine when the UPS is on battery.**
- **Run a script on a schedule.**

"Everything off when the last person leaves" and "Tell me if a door opens while I'm away" need presence, which comes in a later phase. For now they're listed as coming later.

## The Test Center

The Test Center runs an automation or routine **without doing anything real**. Open it from **Automations › Test Center**, or from an automation's **Test** tab, which tests your unsaved changes.

1. Pick what to test.
2. Under **Pretend these devices read**, type values for the devices it uses (for example, UPS runtime 12). Empty boxes use the real current state.
3. Optionally:
   - give trigger details as JSON
   - choose a step to start at (this skips the conditions)
   - give the result a script should pretend to return (otherwise, the sample from the script's header is used)
4. **Run test.**

The summary at the top confirms that nothing happened: "Done. 0 devices changed, 0 messages sent, 0 scripts run." Below it is every step. Steps that would have acted are marked **What if**, with what they would have done.

You need the Test Center feature to run tests (Admins have it).

## Keyboard

The console has no shortcuts of its own. Everything works with Tab, Shift+Tab, Enter, Space, the arrow keys in menus and tabs, and Escape to close dialogs.
