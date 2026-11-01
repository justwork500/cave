import { Textarea } from "@fluentui/react-components";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "../app/prefs";
import { loadMonaco } from "./monaco";

let models = 0;

/**
 * A YAML editor: Monaco with schema hints once it has loaded, a plain text box until then (and if it can't load).
 * Text only ever goes in as a model value, never as markup.
 */
export function YamlEditor({ label, value, onChange, schema = "automation", language = "yaml" }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  schema?: "automation" | "sequence" | "dashboard";
  /** Scripts reuse the editor with their own highlighting and no schema. */
  language?: "yaml" | "powershell" | "python" | "shell";
}) {
  const host = useRef<HTMLDivElement>(null);
  const editor = useRef<import("monaco-editor").editor.IStandaloneCodeEditor>(undefined);
  const latest = useRef(onChange);
  const [ready, setReady] = useState(false);
  const { theme } = useTheme();
  const initial = useRef(value);

  useEffect(() => {
    latest.current = onChange;
  }, [onChange]);

  useEffect(() => {
    let disposed = false;
    loadMonaco().then(
      (monaco) => {
        if (disposed || !host.current) return;
        models += 1;
        // the file name picks the schema (see monacoSetup's fileMatch)
        const name = language === "yaml" ? `${schema}-${models}.yaml` : `script-${models}`;
        const model = monaco.editor.createModel(initial.current, language, monaco.Uri.parse(`file:///${name}`));
        const ed = monaco.editor.create(host.current, {
          model, automaticLayout: true, minimap: { enabled: false }, tabSize: 2, fontSize: 13,
          ariaLabel: label, scrollBeyondLastLine: false,
        });
        ed.onDidChangeModelContent(() => latest.current(ed.getValue()));
        editor.current = ed;
        setReady(true);
      },
      () => undefined, // keep the text box
    );
    return () => {
      disposed = true;
      editor.current?.getModel()?.dispose();
      editor.current?.dispose();
    };
  }, [label, schema, language]);

  useEffect(() => {
    const ed = editor.current;
    if (ed && ed.getValue() !== value) ed.setValue(value);
  }, [value]);

  useEffect(() => {
    void loadMonaco().then((m) => m.editor.setTheme(theme === "dark" ? "vs-dark" : theme === "contrast" ? "hc-black" : "vs"));
  }, [theme]);

  return (
    <div className="yaml-editor">
      <div ref={host} className="monaco-host" hidden={!ready} />
      {!ready && (
        <Textarea
          aria-label={label}
          className="yaml-text"
          resize="vertical"
          value={value}
          spellCheck={false}
          onChange={(_, d) => onChange(d.value)}
        />
      )}
    </div>
  );
}
