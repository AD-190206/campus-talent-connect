import Link from "next/link";
import { Logo, ThemeToggle } from "@/components/brand";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
        <Logo />
        <ThemeToggle />
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pb-16 pt-6 sm:items-center sm:pt-0">
        <div className="w-full max-w-[440px]">{children}</div>
      </main>
      <footer className="pb-6 text-center text-xs text-muted">
        <Link href="/" className="hover:text-fg">
          Campus Talent Connect
        </Link>
      </footer>
    </div>
  );
}
