import { redirect } from "next/navigation";

import { hasSession } from "@/lib/session";

import { LoginForm } from "./login-form";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  if (await hasSession()) redirect("/");
  return (
    <main className="mx-auto mt-24 max-w-sm px-4">
      <h1 className="text-2xl font-semibold">Northwind Talent</h1>
      <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">Recruiter sign in</p>
      <LoginForm />
    </main>
  );
}
