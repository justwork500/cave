/** Monaco and its YAML language server, all from our own origin: the CSP allows no CDN. */
import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import { configureMonacoYaml } from "monaco-yaml";
import YamlWorker from "monaco-yaml/yaml.worker?worker";
import { api } from "../api/client";

window.MonacoEnvironment = {
  getWorker: (_id: string, label: string) => (label === "yaml" ? new YamlWorker() : new EditorWorker()),
};

const NAMES = ["automation", "sequence", "dashboard"] as const;

async function schemas() {
  const loaded = await Promise.all(
    NAMES.map((n) => api.get<object>(`/schemas/${n}.json`).then((schema) => ({ n, schema }), () => null)),
  );
  return loaded.flatMap((s) => (s ? [{ uri: `cave://schemas/${s.n}.json`, fileMatch: [`${s.n}-*`], schema: s.schema }] : []));
}

export async function setup() {
  configureMonacoYaml(monaco, { enableSchemaRequest: false, schemas: await schemas() });
  return monaco;
}
