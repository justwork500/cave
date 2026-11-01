import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { ErrorBar, when } from "./Page";

interface Cert {
  fingerprint: string;
  not_after: string;
  self_signed: boolean;
}

export function Certificate() {
  const cert = useQuery({ queryKey: ["certificate"], queryFn: () => api.get<Cert>("/system/certificate") });
  const c = cert.data;
  return (
    <section className="stack">
      <h2>Certificate</h2>
      <ErrorBar error={cert.error} />
      {c && (
        <>
          <dl className="facts">
            <dt>Fingerprint (SHA-256)</dt>
            <dd><code className="fingerprint">{c.fingerprint}</code></dd>
            <dt>Expires</dt>
            <dd>{when(c.not_after)}</dd>
            <dt>Kind</dt>
            <dd>{c.self_signed ? "Self-signed, made by CAVE" : "Your own certificate"}</dd>
          </dl>
          {c.self_signed && (
            <p>
              Browsers warn about a self-signed certificate. Check the fingerprint above matches the one your browser
              shows. To use your own, start CAVE with <code>--cert</code> and <code>--key</code>, or put it behind a
              reverse proxy and list that proxy under Trusted proxies. The tablet guide has the details.
            </p>
          )}
        </>
      )}
    </section>
  );
}
