import * as React from "react";
import { cn } from "@/lib/utils";

export function PlainInput({
  className,
  ...props
}: React.ComponentProps<"input">) {
  return (
    <input
      data-slot="input-group-control"
      className={cn(
        "h-8 min-w-0 flex-1 rounded-none border-0 bg-transparent px-2.5 text-base outline-none placeholder:text-muted-foreground md:text-sm",
        className,
      )}
      {...props}
    />
  );
}
