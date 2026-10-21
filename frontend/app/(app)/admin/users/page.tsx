"use client";

import { useState } from "react";
import { Search, UserX } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import type { Profile, UserAccount } from "@/lib/types";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Alert } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { DescriptionList, PageHeader, Section } from "@/components/ui/layout";
import { Badge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function AdminUsersPage() {
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [account, setAccount] = useState<UserAccount | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [confirm, setConfirm] = useState(false);

  const lookup = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const id = query.trim();
    if (!UUID.test(id)) {
      setError("Enter a full user ID (UUID).");
      return;
    }
    setPending(true);
    setError(null);
    setAccount(null);
    setProfile(null);
    try {
      const { data } = await api.users.get(id);
      setAccount(data);
      const p = await api.users.profile(id).catch(() => null);
      setProfile(p?.data ?? null);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 404 ? "No user has this ID." : err instanceof ApiError ? err.message : "Lookup failed.");
    } finally {
      setPending(false);
    }
  };

  const profileItems: Array<[string, React.ReactNode]> = profile
    ? "college" in profile
      ? [
          ["Name", profile.name || "—"],
          ["College", profile.college || "—"],
          ["Skills", profile.skills || "—"],
        ]
      : [
          ["Contact", profile.contact_person || "—"],
          ["Company", profile.company_name || "—"],
        ]
    : [];

  return (
    <RoleGate allow={["ADMIN"]}>
      <PageHeader title="Users" description="Look up an account by ID and deactivate it if needed." />
      <Alert tone="info" className="mb-6">
        The User service doesn’t provide a user list or search yet, so accounts can only be opened by ID. User IDs appear
        on projects, applications and assignments.
      </Alert>

      <form onSubmit={lookup} noValidate className="card flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
        <Field label="User ID" error={error ?? undefined} className="flex-1">
          {(id, d) => (
            <Input
              id={id}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. 7b8a9b8a-9f4b-4cb8-a0a6-0c2a0a8c20c1"
              className="font-mono"
              aria-describedby={d}
              aria-invalid={!!error}
            />
          )}
        </Field>
        <Button type="submit" loading={pending} className={error ? "sm:mb-[22px]" : ""}>
          <Search className="h-4 w-4" aria-hidden />
          Look up
        </Button>
      </form>

      {account && (
        <Section
          className="mt-6"
          title={account.email}
          description={`${ROLE_LABEL[account.role]} · joined ${formatDate(account.created_at)}`}
          actions={account.is_active ? <Badge tone="success">Active</Badge> : <Badge tone="danger">Deactivated</Badge>}
        >
          <DescriptionList items={[["User ID", <span key="id" className="font-mono text-xs">{account.user_id}</span>], ...profileItems]} />
          {account.is_active && account.role !== "ADMIN" && (
            <div className="border-t border-line p-5">
              <Button variant="danger" onClick={() => setConfirm(true)}>
                <UserX className="h-4 w-4" aria-hidden />
                Deactivate account
              </Button>
            </div>
          )}
        </Section>
      )}

      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Deactivate this account?"
        description="The user will no longer be able to sign in. There is no reactivation endpoint yet."
        confirmLabel="Deactivate"
        tone="danger"
        onConfirm={async () => {
          await api.users.deactivate(account!.user_id);
          toast("Account deactivated.");
          await lookup();
        }}
      />
    </RoleGate>
  );
}
