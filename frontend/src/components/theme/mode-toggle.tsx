import React from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Sun, Moon, Monitor, Check } from "lucide-react";
import { Button } from "../ui/button";
import { useTheme, type Theme } from "./theme-provider";
import { cn } from "../../lib/utils";

export function ModeToggle() {
  const { theme, setTheme } = useTheme();

  const Item = ({
    value,
    icon: Icon,
    children
  }: {
    value: Theme;
    icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
    children: React.ReactNode;
  }) => (
    <DropdownMenu.Item
      onSelect={() => setTheme(value)}
      className={cn(
        "relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors",
        "focus:bg-accent focus:text-accent-foreground"
      )}
    >
      <Icon className="mr-2 h-4 w-4" />
      {children}
      <span className="ml-auto pl-4 text-muted-foreground">
        {theme === value ? <Check className="h-4 w-4" /> : null}
      </span>
    </DropdownMenu.Item>
  );

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="ghost" size="icon" aria-label="Toggle theme">
          <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          <span className="sr-only">Toggle theme</span>
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          sideOffset={8}
          align="end"
          className={cn(
            "z-50 min-w-[10rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md",
            "data-[side=bottom]:animate-in data-[side=bottom]:fade-in-0 data-[side=bottom]:zoom-in-95"
          )}
        >
          <Item value="light" icon={Sun}>
            Light
          </Item>
          <Item value="dark" icon={Moon}>
            Dark
          </Item>
          <Item value="system" icon={Monitor}>
            System
          </Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
