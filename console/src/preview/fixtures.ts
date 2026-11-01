/**
 * Sample data for the design preview (preview.html): one believable home, so every screen can be looked at
 * and measured without a server or a sign-in. Never used by the real console.
 */

const now = "2026-11-01T09:12:00Z";
const ago = (minutes: number) => new Date(Date.parse(now) - minutes * 60_000).toISOString();

export const me = {
  kind: "user", id: "u-jordan", username: "jordan", display_name: "Jordan", role: "admin", has_totp: true,
  sections: ["section:devices", "section:automations", "section:scripts", "section:dashboards", "section:users",
             "section:system", "section:audit", "section:signin_log", "section:run_history"],
};

export const areas = [
  { id: "living_room", name: "Living room", floor: null },
  { id: "kitchen", name: "Kitchen", floor: null },
  { id: "garage", name: "Garage", floor: null },
  { id: "kids_room", name: "Kids' room", floor: null },
  { id: "office", name: "Office", floor: null },
  { id: "front_yard", name: "Front yard", floor: null },
];

const e = (entity_id: string, name: string, area_id: string | null, state: string, attributes = {}) => ({
  entity_id, name, area_id, capability: entity_id.split(".")[0], state, attributes, last_changed: ago(42),
});

export const states = [
  e("light.living_room", "Ceiling light", "living_room", "on"),
  e("light.reading_lamp", "Reading lamp", "living_room", "off"),
  e("switch.kitchen_kettle", "Kettle", "kitchen", "off"),
  e("sensor.kitchen_temperature", "Temperature", "kitchen", "21.4", { unit: "°C" }),
  e("cover.garage_door", "Garage door", "garage", "closed"),
  e("light.kids_room", "Night light", "kids_room", "on"),
  e("switch.office_heater", "Heater", "office", "unavailable"),
  e("sensor.ups_load_pct", "UPS load", "office", "38", { unit: "%" }),
  e("sensor.ups_battery_runtime_min", "UPS runtime", "office", "46", { unit: "min" }),
  e("binary_sensor.ups_on_battery", "UPS on battery", "office", "off"),
  e("light.porch", "Porch light", "front_yard", "off"),
  e("lock.front_door", "Front door", "front_yard", "locked"),
];

export const dashboardView = {
  slug: "home", title: "Home", icon: null,
  views: [{ id: "main", title: "Home", sections: [
    { title: "Living room", cards: [
      { type: "tile", w: 3, h: 1, entity: states[0], tap_action: "toggle", locked: false },
      { type: "tile", w: 3, h: 1, entity: states[1], tap_action: "toggle", locked: false },
      { type: "tile", w: 3, h: 1, entity: states[10], tap_action: "toggle", locked: false },
      { type: "tile", w: 3, h: 1, entity: states[11], tap_action: "none", locked: false },
    ] },
    { title: "Garage and power", cards: [
      { type: "tile", w: 3, h: 1, entity: { entity_id: "cover.garage_door", name: "Garage door", area_id: "garage",
                                            restricted: true }, tap_action: "toggle", locked: true },
      { type: "gauge", w: 3, h: 2, entity: states[7], min: 0, max: 100, severity: { green: 0, yellow: 60, red: 85 },
        locked: false },
      { type: "entities", w: 3, h: 2, entities: [states[8], states[9], states[3]] },
      { type: "button", w: 3, h: 1, name: "Shut down the lab", action: "sequence.lab_safe_shutdown", entity: null,
        command: null, confirm: true, allowed: true },
      { type: "markdown", w: 6, h: 1, text: "UPS has **46 min** of runtime at the current load." },
    ] },
  ] }],
};

export const items = [
  { id: "dashboard:home", kind: "dashboard", name: "Home", allowed: true, status: "enabled", visibility: "restrict",
    others_see: "none", network: "anywhere", builtin: true },
  { id: "dashboard:kids", kind: "dashboard", name: "Kids", allowed: true, status: "enabled", visibility: "restrict",
    others_see: "locked", network: "anywhere", builtin: false },
  { id: "dashboard:garage", kind: "dashboard", name: "Garage door control", allowed: true, status: "enabled",
    visibility: "restrict", others_see: "locked", network: "local", builtin: false },
  { id: "sequence:lab_safe_shutdown", kind: "action", name: "Lab safe shutdown", allowed: true, status: "enabled",
    visibility: "restrict", others_see: "locked", network: "anywhere", builtin: false },
  { id: "automation:ups-on-battery", kind: "action", name: "UPS on battery", allowed: true, status: "enabled",
    visibility: "restrict", others_see: "none", network: "anywhere", builtin: false },
  { id: "section:devices", kind: "section", name: "Devices", allowed: true, status: "enabled", visibility: "restrict",
    others_see: "none", network: "anywhere", builtin: true },
  { id: "section:users", kind: "section", name: "Users and permissions", allowed: true, status: "enabled",
    visibility: "restrict", others_see: "none", network: "local", builtin: true },
  { id: "feature:test_center", kind: "feature", name: "Test Center", allowed: true, status: "enabled",
    visibility: "restrict", others_see: "none", network: "anywhere", builtin: true },
];

export const assignments: Record<string, { kind: string; id: string }[]> = {
  "dashboard:home": [{ kind: "role", id: "household" }],
  "dashboard:kids": [{ kind: "group", id: "g-kids" }],
  "dashboard:garage": [{ kind: "screen", id: "s-garage" }],
  "sequence:lab_safe_shutdown": [{ kind: "role", id: "admin" }],
  "automation:ups-on-battery": [{ kind: "role", id: "admin" }],
  "section:devices": [{ kind: "role", id: "operator" }],
  "section:users": [{ kind: "role", id: "admin" }],
  "feature:test_center": [{ kind: "role", id: "admin" }],
};

export const users = [
  { id: "u-jordan", username: "jordan", display_name: "Jordan", role: "admin", enabled: true, expires_at: null },
  { id: "u-sam", username: "sam", display_name: "Sam", role: "household", enabled: true, expires_at: null },
  { id: "u-riley", username: "riley", display_name: "Riley", role: "household", enabled: true, expires_at: null },
  { id: "u-casey", username: "casey", display_name: "Casey (sitter)", role: "guest", enabled: true,
    expires_at: "2026-11-15T23:59:59Z" },
];

export const groups = [{ id: "g-kids", name: "Kids", members: ["u-sam", "u-riley"] }];

export const screens = [
  { id: "s-garage", name: "Garage tablet", status: "approved", fingerprint: "3F:9A:12:C0:7B:4E:91:D2",
    created_at: ago(60 * 24 * 9) },
  { id: "s-hall", name: "Hall iPad", status: "pending", fingerprint: "A1:58:0C:E3:44:9F:2B:70", created_at: ago(5) },
];

export const summary = {
  mqtt: { status: "connected", entities: states.length }, unavailable: 1, failures_24h: 0, screens_pending: 1,
};

export const notifications = [
  { id: 3, title: "Power", message: "UPS back on mains after 4 minutes.", source: "automation:ups-on-battery",
    created_at: ago(95), read_at: null },
  { id: 2, title: null, message: "Hall iPad is waiting for approval.", source: "system", created_at: ago(5),
    read_at: null },
];

export const listed = {
  automations: [{ id: "ups-on-battery", name: "UPS on battery", allowed: true },
                { id: "porch-at-dusk", name: "Porch light at dusk", allowed: true }],
  sequences: [{ id: "lab_safe_shutdown", name: "Lab safe shutdown", allowed: true }],
  dashboards: [{ id: "home", name: "Home", allowed: true }, { id: "kids", name: "Kids", allowed: true },
               { id: "garage", name: "Garage door control", allowed: true }],
};

export const automationYaml = `automation:
  id: "ups-on-battery"
  name: "UPS on battery"
  triggers:
    - type: "state"
      entity: "binary_sensor.ups_on_battery"
      to: "on"
      for: "2m"
  conditions:
    - type: "numeric_state"
      entity: "sensor.ups_battery_runtime_min"
      below: 15
  actions:
    - type: "notify"
      message: "UPS on battery"
    - type: "sequence"
      ref: "sequence.lab_safe_shutdown"
`;

export const traces = [
  { id: 4, started_at: ago(95), finished_at: ago(94), trace: { outcome: "finished", variables: {}, error: null,
    steps: [{ path: "actions[0]", type: "notify", detail: "notify: UPS on battery", started_at: ago(95),
              result: "ok", data: {} }] } },
];

export const scripts = [
  { file: "Stop-LabHosts.ps1", name: "Stop lab hosts", language: "ps1", allowed: true },
  { file: "backup-photos.sh", name: "Back up photos", language: "sh", allowed: true },
];

export const script = {
  file: "Stop-LabHosts.ps1", name: "Stop lab hosts", language: "ps1",
  text: "<#\ncave:\n  name: Stop lab hosts\n  timeout: 5m\n  params:\n    GraceSeconds: { type: int, default: 60 }\n#>\nparam([int]$GraceSeconds = 60)\n@{ status = \"3 hosts stopped\" } | ConvertTo-Json -Compress\n",
  header: { name: "Stop lab hosts", target: "sandbox", timeout: "PT5M", secrets: ["PROXMOX_TOKEN"],
            params: { GraceSeconds: { type: "int", default: 60, min: 0, max: 600, choices: null } } },
};

export const scriptRuns = [
  { id: 2, started_by: "user:u-jordan", started_at: ago(30), duration_ms: 2140, outcome: "finished",
    log: ["Stopping media", "Stopping build", "Stopping lab-dc"], result: { status: "3 hosts stopped" } },
];

export const tokens = [{ id: "t1", user_id: "u-jordan", name: "Node-RED", created_at: ago(60 * 24 * 3) }];

export const audit = [
  { time: ago(4), actor: "user:u-jordan", action: "item.assignments", target: "dashboard:kids",
    old: [{ kind: "role", id: "household" }], new: [{ kind: "group", id: "g-kids" }] },
  { time: ago(30), actor: "user:u-jordan", action: "script.run", target: "script:Stop-LabHosts.ps1", old: null,
    new: { outcome: "finished", exit_code: 0 } },
  { time: ago(60 * 26), actor: "user:u-jordan", action: "user.create", target: "user:u-casey", old: null,
    new: { username: "casey", role: "guest" } },
];

export const signins = [
  { username: "jordan", at: ago(12), result: "signed in", ip: "192.168.1.24" },
  { username: "sam", at: ago(60 * 3), result: "signed in", ip: "192.168.1.31" },
  { username: "sam", at: ago(60 * 3 + 1), result: "wrong password", ip: "192.168.1.31" },
];

export const networks = { local_ranges: ["192.168.1.0/24"], trusted_proxies: [] };
export const certificate = { fingerprint: "2E:DB:F2:82:23:42:65:0E:A9:89:10:E4:46:73:32:9A", not_after: "2028-12-04T00:00:00Z",
                             self_signed: true };
export const configErrors = { "automations/porch-at-dusk.yaml": "automations/porch-at-dusk.yaml:6: triggers.0.at: expected a time like 07:30" };
