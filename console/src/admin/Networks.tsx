import { Button, Field, Textarea } from "@fluentui/react-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, message } from "../api/client";
import { ErrorBar } from "./Page";

interface Nets {
  local_ranges: string[];
  trusted_proxies: string[];
}

const lines = (s: string) => s.split(/[\n,]/).map((x) => x.trim()).filter(Boolean);

/** Which addresses count as "local network", and which proxies CAVE believes. */
export function Networks() {
  const client = useQueryClient();
  const nets = useQuery({ queryKey: ["networks"], queryFn: () => api.get<Nets>("/system/networks") });
  const [edit, setEdit] = useState<{ ranges: string; proxies: string }>();
  const ranges = edit?.ranges ?? nets.data?.local_ranges.join("\n") ?? "";
  const proxies = edit?.proxies ?? nets.data?.trusted_proxies.join("\n") ?? "";
  const save = useMutation({
    mutationFn: () => api.put<Nets>("/system/networks", { local_ranges: lines(ranges), trusted_proxies: lines(proxies) }),
    onSuccess: (n) => {
      client.setQueryData(["networks"], n);
      setEdit(undefined);
    },
  });
  const problem = save.isError ? message(save.error) : undefined;
  // the API names the bad value; show the message under the box that holds it
  const inProxies = problem !== undefined && lines(proxies).some((p) => problem.includes(p));
  return (
    <form className="stack" onSubmit={(e) => {
      e.preventDefault();
      save.mutate();
    }}>
      <h2>Networks</h2>
      <ErrorBar error={nets.error} />
      <Field label="Local network ranges" hint="One range per line, like 192.168.1.0/24. Items set to Local only work from these."
             validationMessage={!inProxies ? problem : undefined}>
        <Textarea value={ranges} onChange={(_, d) => setEdit({ ranges: d.value, proxies })} />
      </Field>
      <Field label="Trusted proxies" hint="Only if CAVE sits behind a reverse proxy. Leave empty otherwise."
             validationMessage={inProxies ? problem : undefined}>
        <Textarea value={proxies} onChange={(_, d) => setEdit({ ranges, proxies: d.value })} />
      </Field>
      <div className="row start">
        <Button appearance="primary" type="submit" disabled={save.isPending}>
          Save networks
        </Button>
        {save.isSuccess && <span role="status">Saved.</span>}
      </div>
    </form>
  );
}
