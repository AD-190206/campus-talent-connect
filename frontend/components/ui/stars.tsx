import { Star } from "lucide-react";
import { cn } from "@/lib/format";

export function Stars({ rating, className }: { rating: number; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-0.5", className)} aria-label={`${rating} out of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Star
          key={n}
          aria-hidden
          className={cn("h-4 w-4", n <= rating ? "fill-warning text-warning" : "text-line-strong")}
        />
      ))}
    </span>
  );
}
