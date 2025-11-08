import React from "react";
import { cn } from "../../lib/utils";

type Ctx = { close: () => void };
const DropdownCtx = React.createContext<Ctx | null>(null);

export function Dropdown({
  trigger,
  align = "end",
  children,
  className
}: {
  trigger: React.ReactElement;
  align?: "start" | "end";
  children: React.ReactNode;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const triggerEl = React.cloneElement(trigger, {
    onClick: (e: React.MouseEvent) => {
      e.stopPropagation();
      setOpen((o: boolean) => !o);
      if (typeof trigger.props.onClick === "function") trigger.props.onClick(e);
    },
    "aria-haspopup": "menu",
    "aria-expanded": open
  });

  return (
    <div className={cn("relative inline-block text-left", className)} ref={ref}>
      {triggerEl}
      {open ? (
        <div
          className={cn(
            "absolute z-50 mt-1 min-w-[160px] rounded-md border bg-popover text-popover-foreground shadow-md focus:outline-none",
            align === "end" ? "right-0" : "left-0"
          )}
        >
          <DropdownCtx.Provider value={{ close: () => setOpen(false) }}>
            <div className="p-1" role="menu">{children}</div>
          </DropdownCtx.Provider>
        </div>
      ) : null}
    </div>
  );
}

export function DropdownItem({
  onSelect,
  children,
  disabled,
  variant = "default"
}: {
  onSelect?: () => void | Promise<void>;
  children: React.ReactNode;
  disabled?: boolean;
  variant?: "default" | "destructive";
}) {
  const ctx = React.useContext(DropdownCtx);
  const handleClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (disabled) return;
    await onSelect?.();
    ctx?.close();
  };
  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled}
      className={cn(
        "w-full select-none rounded px-2 py-1.5 text-left text-sm outline-none transition",
        "hover:bg-muted focus:bg-muted",
        disabled && "opacity-50 cursor-not-allowed",
        variant === "destructive" ? "text-red-600 hover:text-red-700" : ""
      )}
      role="menuitem"
    >
      {children}
    </button>
  );
}

export function DropdownSeparator() {
  return <div className="my-1 h-px bg-border" role="separator" />;
}
