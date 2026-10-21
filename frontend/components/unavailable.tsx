import { Construction } from "lucide-react";

/** Honest placeholder for features the backend does not support yet. */
export function Unavailable({
  title,
  description,
  needs,
}: {
  title: string;
  description: string;
  needs: string[];
}) {
  return (
    <div className="card p-6 sm:p-8">
      <div className="flex items-start gap-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-2 text-muted">
          <Construction className="h-5 w-5" aria-hidden />
        </span>
        <div>
          <h2 className="text-[15px] font-semibold">{title}</h2>
          <p className="mt-1 max-w-xl text-sm text-muted">{description}</p>
          <p className="label-caps mt-6">Needs backend support</p>
          <ul className="mt-2 space-y-1.5">
            {needs.map((n) => (
              <li key={n} className="font-mono text-[13px] text-fg">
                {n}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
