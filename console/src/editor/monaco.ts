/** Loads Monaco on first use, so the dashboard never downloads it. */
let loading: Promise<typeof import("monaco-editor")> | undefined;

export function loadMonaco() {
  loading ??= import("./monacoSetup").then((m) => m.setup());
  return loading;
}
