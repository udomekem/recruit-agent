import { requireSession } from "@/lib/session";

import { Brand } from "../brand";
import { logout } from "./actions";
import { Nav } from "./nav";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  await requireSession();
  return (
    <div className="h-app">
      <a href="#main" className="h-skip">
        Skip to content
      </a>
      <header className="h-header">
        <Brand />
        <div className="h-crumb">
          Northwind Talent <span aria-hidden="true">/</span> <b>Recruitment</b>
        </div>
        <Nav />
        <div className="h-account">
          <p className="who" style={{ margin: 0, fontSize: 12, fontWeight: 600 }}>
            Recruiter
          </p>
          <span className="h-avatar" aria-hidden="true">
            NT
          </span>
          <form action={logout}>
            <button type="submit" className="h-linkbtn">
              Sign out
            </button>
          </form>
        </div>
      </header>
      <main id="main" className="h-content">
        {children}
      </main>
    </div>
  );
}
