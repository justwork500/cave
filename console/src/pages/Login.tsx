import { Button, Field, Input, MessageBar, MessageBarBody } from "@fluentui/react-components";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { api, message } from "../api/client";
import { Mark } from "../app/shell/MenuBar";
import { Authenticator, type Enrollment } from "./Authenticator";

/** Only same-site paths, so a crafted link can't bounce you elsewhere after signing in. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}

export function AuthFrame({ children }: { children: React.ReactNode }) {
  return (
    <main className="auth">
      <div className="auth-panel">
        <p className="wordmark" aria-hidden="true"><Mark />CAVE</p>
        {children}
      </div>
    </main>
  );
}

function ErrorText({ error }: { error: unknown }) {
  return (
    <MessageBar intent="error" role="alert">
      <MessageBarBody>{message(error)}</MessageBarBody>
    </MessageBar>
  );
}

export function Login() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const done = () => navigate(safeNext(params.get("next")), { replace: true });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");

  const login = useMutation({
    mutationFn: () => api.post<{ mfa_required: boolean; mfa_setup?: boolean }>("/auth/login", { username, password }),
    onSuccess: (r) => {
      if (!r.mfa_required) done();
      else if (r.mfa_setup) enroll.mutate();
    },
  });
  const enroll = useMutation({ mutationFn: () => api.post<Enrollment>("/auth/mfa/setup") });
  const mfa = useMutation({ mutationFn: () => api.post("/auth/mfa", { code: code.trim() }), onSuccess: done });
  const setup = useQuery({ queryKey: ["setup"], queryFn: () => api.get<{ needed: boolean }>("/setup") });

  if (setup.data?.needed) return <Navigate to="/setup" replace />;

  if (enroll.data) {
    return (
      <AuthFrame>
        <Authenticator enrollment={enroll.data} onDone={done} />
      </AuthFrame>
    );
  }

  if (login.data?.mfa_required && !login.data.mfa_setup) {
    return (
      <AuthFrame>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            mfa.mutate();
          }}
        >
          <h1>Enter your code</h1>
          <Field label="Code from your authenticator app" hint="A recovery code works here too.">
            <Input value={code} onChange={(_, d) => setCode(d.value)} autoComplete="one-time-code" autoFocus />
          </Field>
          {mfa.isError && <ErrorText error={mfa.error} />}
          <Button appearance="primary" type="submit" disabled={!code.trim() || mfa.isPending}>
            Continue
          </Button>
        </form>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate();
        }}
      >
        <h1>Sign in</h1>
        <Field label="Username">
          <Input value={username} onChange={(_, d) => setUsername(d.value)} autoComplete="username" />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            value={password}
            onChange={(_, d) => setPassword(d.value)}
            autoComplete="current-password"
          />
        </Field>
        {(login.isError || enroll.isError) && <ErrorText error={login.error ?? enroll.error} />}
        <Button appearance="primary" type="submit" disabled={!username || !password || login.isPending}>
          Sign in
        </Button>
      </form>
    </AuthFrame>
  );
}
