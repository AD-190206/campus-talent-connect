"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { Field, Input, PasswordInput } from "@/components/ui/field";

/** Only allow redirects to in-app paths. */
function safeNext(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

function LoginForm() {
  const { login, status } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (status === "authenticated" && !pending) router.replace(next);
  }, [status, pending, next, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const nextErrors: typeof errors = {};
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) nextErrors.email = "Enter a valid email address.";
    if (!password) nextErrors.password = "Enter your password.";
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;

    setPending(true);
    setFormError(null);
    try {
      await login(email.trim(), password);
      router.replace(next);
    } catch (err) {
      setFormError(
        err instanceof ApiError && err.status === 401
          ? "That email and password don’t match an active account."
          : err instanceof ApiError
            ? err.message
            : "Sign-in failed. Please try again."
      );
      setPending(false);
    }
  };

  return (
    <div className="card p-6 sm:p-8">
      <h1 className="text-xl font-semibold tracking-tight">Welcome back</h1>
      <p className="mt-1 text-sm text-muted">Sign in to continue to your workspace.</p>

      {params.get("expired") && (
        <Alert tone="info" className="mt-5">
          Your session expired. Please sign in again.
        </Alert>
      )}
      {params.get("registered") && (
        <Alert tone="success" className="mt-5">
          Account created. Sign in to get started.
        </Alert>
      )}
      {formError && <Alert className="mt-5">{formError}</Alert>}

      <form onSubmit={submit} noValidate className="mt-6 space-y-4">
        <Field label="Email" error={errors.email}>
          {(id, describedBy) => (
            <Input
              id={id}
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={!!errors.email}
              aria-describedby={describedBy}
              autoFocus
            />
          )}
        </Field>
        <Field label="Password" error={errors.password}>
          {(id, describedBy) => (
            <PasswordInput
              id={id}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={!!errors.password}
              aria-describedby={describedBy}
            />
          )}
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={pending}>
          Sign in
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        New to CTC?{" "}
        <Link href="/register" className="font-medium text-fg underline-offset-4 hover:underline">
          Create an account
        </Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
