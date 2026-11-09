"use server";

import { redirect } from "next/navigation";

import { signIn } from "@/lib/session";

export type LoginState = { error?: string };

export async function login(_prev: LoginState, form: FormData): Promise<LoginState> {
  const result = await signIn(String(form.get("password") ?? ""));
  if (!result.ok) return { error: result.error };
  redirect("/");
}
