import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "bg-primary/10 text-primary border-transparent",
        secondary: "bg-secondary text-secondary-foreground border-transparent",
        outline: "text-foreground",
        success: "bg-emerald-500/10 text-emerald-600 border-emerald-200 dark:border-emerald-700",
        warning: "bg-amber-500/10 text-amber-600 border-amber-200 dark:border-amber-700",
        destructive: "bg-red-500/10 text-red-600 border-red-200 dark:border-red-700",
        muted: "bg-muted text-muted-foreground border-transparent"
      }
    },
    defaultVariants: {
      variant: "default"
    }
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
