"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { LogOut } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { ROLE_LABEL, useAuth, useUser } from "@/lib/auth";
import { ThemeSelector } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/layout";
import { useToast } from "@/components/ui/toast";

function Block({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-b border-line py-8 first:pt-0 last:border-0 md:grid-cols-[240px_1fr] md:gap-10">
      <div>
        <h2 className="text-[15px] font-semibold">{title}</h2>
        <p className="mt-1 text-[13px] text-muted">{description}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

export default function SettingsPage() {
  const user = useUser();
  const { logout, updateUser } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [email, setEmail] = useState(user.email);
  const [emailError, setEmailError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [deactivate, setDeactivate] = useState(false);

  const saveEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setEmailError("Enter a valid email address.");
      return;
    }
    setSaving(true);
    setEmailError(undefined);
    try {
      const { data } = await api.users.update(user.user_id, { email: email.trim() });
      updateUser({ email: data.email });
      toast("Email updated. Use it the next time you sign in.");
    } catch (err) {
      setEmailError(err instanceof ApiError ? (err.fieldErrors.email ?? err.message) : "Email could not be updated.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Settings" description="Appearance, account and session." />
      <div className="card px-5 py-8 sm:px-8">
        <Block title="Appearance" description="Choose a theme, or follow your device setting.">
          <ThemeSelector />
        </Block>

        <Block title="Account" description={`${ROLE_LABEL[user.role]} account`}>
          <form onSubmit={saveEmail} noValidate className="flex flex-col gap-3 sm:flex-row sm:items-start">
            <Field label="Email" error={emailError} className="flex-1">
              {(id, d) => (
                <Input
                  id={id}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={!!emailError}
                  aria-describedby={d}
                />
              )}
            </Field>
            <Button type="submit" variant="secondary" loading={saving} disabled={email.trim() === user.email} className="sm:mt-[26px]">
              Update email
            </Button>
          </form>
        </Block>

        <Block title="Session" description="Sign out on this device. Your refresh token is revoked.">
          <Button
            variant="secondary"
            onClick={async () => {
              await logout();
              router.replace("/login");
            }}
          >
            <LogOut className="h-4 w-4" aria-hidden />
            Sign out
          </Button>
        </Block>

        {user.role !== "ADMIN" && (
          <Block title="Deactivate account" description="You won’t be able to sign in again. Contact an administrator to restore access.">
            <Button variant="danger" onClick={() => setDeactivate(true)}>
              Deactivate account
            </Button>
          </Block>
        )}
      </div>

      <ConfirmDialog
        open={deactivate}
        onClose={() => setDeactivate(false)}
        title="Deactivate your account?"
        description="You’ll be signed out and won’t be able to sign in again. Your applications, work and payment records are kept."
        confirmLabel="Deactivate"
        tone="danger"
        onConfirm={async () => {
          await api.users.deactivate(user.user_id);
          await logout();
          router.replace("/");
        }}
      />
    </div>
  );
}
