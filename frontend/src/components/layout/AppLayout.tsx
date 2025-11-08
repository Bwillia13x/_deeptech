import React from "react";
import { Link, NavLink } from "react-router-dom";
import { ModeToggle } from "../theme/mode-toggle";
import { Button } from "../ui/button";
import { cn } from "../../lib/utils";
import { Rocket, Github } from "lucide-react";
import { toast } from "sonner";

type Props = { children: React.ReactNode };

export default function AppLayout({ children }: Props) {
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1">
        <div className="container py-6">{children}</div>
      </main>
      <footer className="border-t">
        <div className="container py-6 text-sm text-muted-foreground">
          © {new Date().getFullYear()} Signal Harvester
        </div>
      </footer>
    </div>
  );
}

function Header() {
  return (
    <header className="border-b">
      <div className="container flex h-14 items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-md bg-primary" />
            <span className="font-semibold tracking-tight">Signal Harvester</span>
          </Link>

          <nav className="ml-2 hidden md:flex items-center gap-1">
            <TopNavLink to="/dashboard">Dashboard</TopNavLink>
            <TopNavLink to="/signals">Signals</TopNavLink>
            <TopNavLink to="/snapshots">Snapshots</TopNavLink>
            <TopNavLink to="/settings">Settings</TopNavLink>
          </nav>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              toast("Hello!", {
                description: "UI shell loaded successfully.",
                icon: <Rocket className="h-4 w-4 text-primary" />
              })
            }
          >
            Test toast
          </Button>
          <ModeToggle />
          <a
            href="https://github.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1"
            aria-label="GitHub"
            title="GitHub"
          >
            <Button variant="ghost" size="icon">
              <Github className="h-5 w-5" />
            </Button>
          </a>
        </div>
      </div>
    </header>
  );
}

function TopNavLink({
  to,
  children
}: {
  to: string;
  children: React.ReactNode;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground",
          "rounded-md transition-colors",
          isActive && "text-foreground bg-accent"
        )
      }
    >
      {children}
    </NavLink>
  );
}
