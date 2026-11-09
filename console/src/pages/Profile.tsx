import {
  Button, Field, Input, MessageBar, MessageBarBody, Radio, RadioGroup, Select,
} from "@fluentui/react-components";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, message } from "../api/client";
import type { Item } from "../api/types";
import { load, save, useTheme } from "../app/prefs";
import type { ThemeName } from "../app/theme";

const MIN_PASSWORD = 12;

export function Profile() {
  const { theme, setTheme } = useTheme();
  const items = useQuery({ queryKey: ["items"], queryFn: () => api.get<Item[]>("/items") });
  const dashboards = (items.data ?? []).filter((i) => i.kind === "dashboard" && i.allowed && !i.missing);
  const [home, setHome] = useState(load("defaultDashboard") ?? "");
  const [pw, setPw] = useState({ current: "", new: "" });
  const change = useMutation({
    mutationFn: () => api.post("/me/password", pw),
    onSuccess: () => setPw({ current: "", new: "" }),
  });

  return (
    <section className="page narrow stack">
      <h1>Profile</h1>

      <h2>Theme</h2>
      <RadioGroup
        aria-label="Theme"
        value={theme}
        onChange={(_, d) => {
          setTheme(d.value as ThemeName);
          save("theme", d.value);
        }}
      >
        <Radio value="light" label="Light" />
        <Radio value="dark" label="Dark" />
        <Radio value="contrast" label="High contrast" />
      </RadioGroup>

      <h2>Your dashboard</h2>
      <Field label="Open this dashboard first" hint="Kept in this browser only.">
        <Select
          value={home}
          onChange={(_, d) => {
            setHome(d.value);
            save("defaultDashboard", d.value);
          }}
        >
          <option value="">The household default</option>
          {dashboards.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
      </Field>

      <h2>Password</h2>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          change.mutate();
        }}
      >
        <Field label="Current password">
          <Input
            type="password"
            value={pw.current}
            onChange={(_, d) => setPw({ ...pw, current: d.value })}
            autoComplete="current-password"
          />
        </Field>
        <Field label="New password" hint={`At least ${MIN_PASSWORD} characters. Other browsers get signed out.`}>
          <Input
            type="password"
            value={pw.new}
            onChange={(_, d) => setPw({ ...pw, new: d.value })}
            autoComplete="new-password"
          />
        </Field>
        {change.isError && (
          <MessageBar intent="error" role="alert">
            <MessageBarBody>{message(change.error)}</MessageBarBody>
          </MessageBar>
        )}
        {change.isSuccess && (
          <MessageBar intent="success">
            <MessageBarBody>Password changed.</MessageBarBody>
          </MessageBar>
        )}
        <Button
          appearance="primary"
          type="submit"
          disabled={!pw.current || pw.new.length < MIN_PASSWORD || change.isPending}
        >
          Change password
        </Button>
      </form>
    </section>
  );
}
