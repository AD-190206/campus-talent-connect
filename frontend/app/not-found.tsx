import { Compass } from "lucide-react";
import { Logo } from "@/components/brand";
import { ButtonLink } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mx-auto flex h-16 w-full max-w-6xl items-center px-6">
        <Logo />
      </header>
      <main className="flex flex-1 flex-col items-center justify-center px-6 pb-24 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 text-muted">
          <Compass className="h-6 w-6" aria-hidden />
        </span>
        <p className="label-caps mt-6">404</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">This page doesn’t exist</h1>
        <p className="mt-2 max-w-sm text-sm text-muted">
          The link may be outdated, or the page may have moved.
        </p>
        <div className="mt-6 flex gap-2">
          <ButtonLink href="/">Go home</ButtonLink>
          <ButtonLink href="/dashboard" variant="secondary">
            Open dashboard
          </ButtonLink>
        </div>
      </main>
    </div>
  );
}
