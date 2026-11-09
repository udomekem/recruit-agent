// Vercel ready check (phase 4 brief): no secret may be exposed to browser code.
// Fails when any source file uses a NEXT_PUBLIC_ variable, or when a client component
// ("use client") reads process.env or imports the server only API or session modules.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const roots = ["app", "lib"];
const problems = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(ts|tsx|mjs|js)$/.test(name) && !name.endsWith(".test.ts")) check(p);
  }
}

function check(file) {
  const src = readFileSync(file, "utf8");
  if (/NEXT_PUBLIC_/.test(src)) problems.push(`${file}: uses a NEXT_PUBLIC_ variable`);
  const client = /^\s*["']use client["']/.test(src);
  if (client && /process\.env/.test(src)) problems.push(`${file}: client code reads process.env`);
  // type only imports are erased at build time, so they are allowed
  if (client && /^import (?!type\b)[^;]*["']@\/lib\/(api|session)["']/m.test(src)) {
    problems.push(`${file}: client code imports a server only module`);
  }
}

roots.forEach(walk);
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}
console.log("no secrets exposed to browser code");
