"use client";

import { Lock } from "lucide-react";
import { useUser } from "@/lib/auth";
import type { Role } from "@/lib/types";
import { ButtonLink } from "./ui/button";
import { EmptyState } from "./ui/feedback";

/**
 * Shows children only to the listed roles. This is a UX guard; the backend
 * enforces authorization on every request.
 */
export function RoleGate({ allow, children }: { allow: Role[]; children: React.ReactNode }) {
  const user = useUser();
  if (allow.includes(user.role)) return <>{children}</>;
  return (
    <div className="card">
      <EmptyState
        icon={Lock}
        title="Not available for your account"
        description="This page is for a different type of account. Use the navigation to find what you need."
        action={
          <ButtonLink href="/dashboard" variant="secondary">
            Back to overview
          </ButtonLink>
        }
      />
    </div>
  );
}
