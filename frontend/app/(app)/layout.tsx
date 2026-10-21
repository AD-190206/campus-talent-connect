"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { AppShell } from "@/components/shell/app-shell";
import { Spinner } from "@/components/ui/feedback";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { status, expired } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "anonymous") {
      const params = new URLSearchParams({ next: pathname });
      if (expired) params.set("expired", "1");
      router.replace(`/login?${params}`);
    }
  }, [status, expired, pathname, router]);

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner label={status === "loading" ? "Loading your workspace" : "Redirecting to sign in"} />
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
