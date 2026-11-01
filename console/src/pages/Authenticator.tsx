import { Button, Checkbox, Field, Input, MessageBar, MessageBarBody } from "@fluentui/react-components";
import { useMutation } from "@tanstack/react-query";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { api, message } from "../api/client";

export interface Enrollment {
  provisioning_uri: string;
  recovery_codes: string[];
}

/** Scan the QR code, prove it with a code, then keep the recovery codes. Used by setup and by sign-in. */
export function Authenticator({ enrollment, onDone }: { enrollment: Enrollment; onDone: () => void }) {
  const [qr, setQr] = useState<string>();
  const [code, setCode] = useState("");
  const [saved, setSaved] = useState(false);
  const verify = useMutation({ mutationFn: () => api.post("/auth/mfa", { code: code.trim() }) });
  const secret = new URL(enrollment.provisioning_uri).searchParams.get("secret") ?? "";

  useEffect(() => {
    QRCode.toDataURL(enrollment.provisioning_uri, { margin: 1, width: 200 }).then(setQr, () => setQr(undefined));
  }, [enrollment.provisioning_uri]);

  if (verify.isSuccess) {
    return (
      <div className="stack">
        <h2>Keep your recovery codes</h2>
        <p>
          Each code signs you in once if you lose your phone. They won't be shown again, so print them or keep them
          in a password manager.
        </p>
        <ul className="codes">
          {enrollment.recovery_codes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <Checkbox
          label="I've saved these codes somewhere safe"
          checked={saved}
          onChange={(_, d) => setSaved(Boolean(d.checked))}
        />
        <Button appearance="primary" disabled={!saved} onClick={onDone}>
          Go to CAVE
        </Button>
      </div>
    );
  }

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        verify.mutate();
      }}
    >
      <h2>Set up your authenticator app</h2>
      <p>Scan this with an authenticator app, or type the key in by hand.</p>
      {qr && <img className="qr" src={qr} width={200} height={200} alt="QR code for your authenticator app" />}
      <p>
        Key: <code className="secret">{secret}</code>
      </p>
      <Field label="Code from your authenticator app">
        <Input value={code} onChange={(_, d) => setCode(d.value)} autoComplete="one-time-code" inputMode="numeric" />
      </Field>
      {verify.isError && (
        <MessageBar intent="error" role="alert">
          <MessageBarBody>{message(verify.error)}</MessageBarBody>
        </MessageBar>
      )}
      <Button appearance="primary" type="submit" disabled={!code.trim() || verify.isPending}>
        Continue
      </Button>
    </form>
  );
}
