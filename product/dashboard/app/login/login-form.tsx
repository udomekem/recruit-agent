"use client";

import { useActionState } from "react";

import { login, type LoginState } from "./actions";

export function LoginForm() {
  const [state, action, pending] = useActionState<LoginState, FormData>(login, {});
  return (
    <form action={action} style={{ marginTop: 20 }}>
      <label htmlFor="password" className="h-label">
        Password
      </label>
      <input
        id="password"
        name="password"
        type="password"
        autoComplete="current-password"
        required
        autoFocus
        className="h-input"
        aria-describedby={state.error ? "login-error" : undefined}
      />
      {state.error ? (
        <p id="login-error" role="alert" className="h-error">
          {state.error}
        </p>
      ) : null}
      <button type="submit" disabled={pending} className="h-btn primary" style={{ width: "100%", marginTop: 18 }}>
        {pending ? "Signing in" : "Sign in"}
      </button>
    </form>
  );
}
