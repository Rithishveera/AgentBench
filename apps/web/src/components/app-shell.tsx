import Link from "next/link";
import { Bot, ChartNoAxesCombined, CirclePlus, ShieldCheck } from "lucide-react";
import { Wordmark } from "@/components/ui/wordmark";

const links = [
  { href: "/", label: "Leaderboard", icon: ChartNoAxesCombined },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/benchmarks/new", label: "New benchmark", icon: CirclePlus },
];

export function AppShell({
  children,
  active,
}: Readonly<{ children: React.ReactNode; active: string }>) {
  return (
    <div className="app-frame">
      <aside className="sidebar">
        <div className="brand">
          <Wordmark size="sm" href="/" />
        </div>
        <p className="nav-label">Workspace</p>
        <nav className="nav-list" aria-label="Main navigation">
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              className="nav-link"
              href={href}
              aria-current={active === href ? "page" : undefined}
              title={label}
            >
              <Icon size={17} aria-hidden="true" />
              <span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-foot">Resilience is measured, not assumed.</div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <span className="topbar-kicker">Agent performance, in context</span>
          <span className="topbar-status"><ShieldCheck size={15} aria-hidden="true" /><span>Private workspace</span></span>
        </header>
        <main className="content">{children}</main>
      </div>
      <nav className="mobile-nav" aria-label="Main navigation">
        {links.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} aria-current={active === href ? "page" : undefined}>
            <Icon size={18} aria-hidden="true" />{label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
