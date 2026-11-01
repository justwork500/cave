import { Button, Field, Input, MessageBar, MessageBarBody, Spinner } from "@fluentui/react-components";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { api, message } from "../api/client";
import { Authenticator, type Enrollment } from "./Authenticator";
import { AuthFrame } from "./Login";

const MIN_PASSWORD = 12;

function strength(pw: string): string {
  if (pw.length < MIN_PASSWORD) return `Use at least ${MIN_PASSWORD} characters.`;
  if (pw.length < 16) return "Good. A longer passphrase is even better.";
  return "Strong.";
}

/** First run: setup code, owner account, authenticator, recovery codes. */
export function Setup() {
  const navigate = useNavigate();
  const needed = useQuery({ queryKey: ["setup"], queryFn: () => api.get<{ needed: boolean }>("/setup") });
  const [code, setCode] = useState("");
  const [codeEntered, setCodeEntered] = useState(false);
  const [owner, setOwner] = useState({ display_name: "", username: "", password: "" });
  const create = useMutation({ mutationFn: () => api.post<Enrollment>("/setup", { code: code.trim(), ...owner }) });

  if (needed.isPending) return <Spinner label="Loading" />;
  if (needed.data && !needed.data.needed) return <Navigate to="/login" replace />;

  if (create.data) {
    return (
      <AuthFrame>
        <Authenticator enrollment={create.data} onDone={() => navigate("/", { replace: true })} />
      </AuthFrame>
    );
  }

  if (!codeEntered) {
    return (
      <AuthFrame>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            setCodeEntered(true);
          }}
        >
          <h1>Set up CAVE</h1>
          <p>The setup code is printed in the server's console when CAVE starts for the first time.</p>
          <Field label="Setup code">
            <Input value={code} onChange={(_, d) => setCode(d.value)} autoComplete="off" autoFocus />
          </Field>
          <Button appearance="primary" type="submit" disabled={!code.trim()}>
            Next
          </Button>
        </form>
      </AuthFrame>
    );
  }

  const set = (k: keyof typeof owner) => (_: unknown, d: { value: string }) => setOwner({ ...owner, [k]: d.value });
  const short = owner.password.length < MIN_PASSWORD;
  return (
    <AuthFrame>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <h1>Create the owner account</h1>
        <p>The owner can change everything in CAVE, including who else can.</p>
        <Field label="Your name">
          <Input value={owner.display_name} onChange={set("display_name")} autoComplete="name" />
        </Field>
        <Field label="Username">
          <Input value={owner.username} onChange={set("username")} autoComplete="username" />
        </Field>
        <Field
          label="Password"
          hint={strength(owner.password)}
          validationState={owner.password && short ? "warning" : "none"}
        >
          <Input type="password" value={owner.password} onChange={set("password")} autoComplete="new-password" />
        </Field>
        {create.isError && (
          <MessageBar intent="error" role="alert">
            <MessageBarBody>{message(create.error)}</MessageBarBody>
          </MessageBar>
        )}
        <div className="row">
          <Button onClick={() => setCodeEntered(false)}>Back</Button>
          <Button appearance="primary" type="submit" disabled={!owner.username || short || create.isPending}>
            Create owner account
          </Button>
        </div>
      </form>
    </AuthFrame>
  );
}
