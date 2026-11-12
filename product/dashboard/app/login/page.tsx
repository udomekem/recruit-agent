import { redirect } from "next/navigation";

import { hasSession } from "@/lib/session";

import { Brand } from "../brand";
import { LoginForm } from "./login-form";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  if (await hasSession()) redirect("/");
  return (
    <main className="h-login">
      <Brand />
      <h1 className="h-h1" style={{ fontSize: 26, marginTop: 24 }}>
        Northwind Talent
      </h1>
      <p className="h-intro">Recruiter sign in</p>
      <LoginForm />
    </main>
  );
}
