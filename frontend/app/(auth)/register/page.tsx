"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Briefcase, GraduationCap } from "lucide-react";
import { api, ApiError, type RegisterInput } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { Field, Input, PasswordInput } from "@/components/ui/field";

type AccountRole = "STUDENT" | "CLIENT";

const ROLE_OPTIONS: Array<{ value: AccountRole; title: string; text: string; icon: typeof Briefcase }> = [
  { value: "STUDENT", title: "I’m a student", text: "Find projects and get paid", icon: GraduationCap },
  { value: "CLIENT", title: "I’m hiring", text: "Post projects, hire students", icon: Briefcase },
];

function RegisterForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { login } = useAuth();
  const [role, setRole] = useState<AccountRole>(params.get("role") === "client" ? "CLIENT" : "STUDENT");
  const [values, setValues] = useState({
    email: "",
    password: "",
    name: "",
    college: "",
    contact_person: "",
    company_name: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const set = (key: keyof typeof values) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  const validate = () => {
    const next: Record<string, string> = {};
    if (role === "STUDENT" && !values.name.trim()) next.name = "Enter your full name.";
    if (role === "CLIENT" && !values.contact_person.trim()) next.contact_person = "Enter a contact name.";
    if (!/^\S+@\S+\.\S+$/.test(values.email.trim())) next.email = "Enter a valid email address.";
    if (values.password.length < 8) next.password = "Use at least 8 characters.";
    return next;
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const nextErrors = validate();
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;

    const body: RegisterInput =
      role === "STUDENT"
        ? {
            role,
            email: values.email.trim(),
            password: values.password,
            name: values.name.trim(),
            college: values.college.trim(),
          }
        : {
            role,
            email: values.email.trim(),
            password: values.password,
            contact_person: values.contact_person.trim(),
            company_name: values.company_name.trim(),
          };

    setPending(true);
    setFormError(null);
    try {
      await api.auth.register(body);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) {
        setErrors(err.fieldErrors);
        setFormError("Please fix the highlighted fields.");
      } else {
        setFormError(err instanceof ApiError ? err.message : "Registration failed. Please try again.");
      }
      setPending(false);
      return;
    }

    try {
      await login(body.email, body.password);
      router.replace(role === "STUDENT" ? "/profile?welcome=1" : "/dashboard");
    } catch {
      router.replace("/login?registered=1");
    }
  };

  const field = (key: keyof typeof values, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}, optional = false) => (
    <Field label={label} error={errors[key]} optional={optional}>
      {(id, describedBy) => (
        <Input
          id={id}
          value={values[key]}
          onChange={set(key)}
          aria-invalid={!!errors[key]}
          aria-describedby={describedBy}
          {...props}
        />
      )}
    </Field>
  );

  return (
    <div className="card p-6 sm:p-8">
      <h1 className="text-xl font-semibold tracking-tight">Create your account</h1>
      <p className="mt-1 text-sm text-muted">Choose how you’ll use Campus Talent Connect.</p>

      <div role="radiogroup" aria-label="Account type" className="mt-6 grid grid-cols-2 gap-3">
        {ROLE_OPTIONS.map(({ value, title, text, icon: Icon }) => {
          const checked = role === value;
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={checked}
              onClick={() => {
                setRole(value);
                setErrors({});
              }}
              className={cn(
                "rounded-xl border p-3.5 text-left transition-colors",
                checked ? "border-primary bg-accent" : "border-line hover:bg-surface-2"
              )}
            >
              <Icon className={cn("h-5 w-5", checked ? "text-accent-fg" : "text-muted")} aria-hidden />
              <p className={cn("mt-2 text-sm font-medium", checked ? "text-accent-fg" : "text-fg")}>{title}</p>
              <p className="mt-0.5 text-xs text-muted">{text}</p>
            </button>
          );
        })}
      </div>

      {formError && <Alert className="mt-5">{formError}</Alert>}

      <form onSubmit={submit} noValidate className="mt-6 space-y-4">
        {role === "STUDENT" ? (
          <>
            {field("name", "Full name", { autoComplete: "name" })}
            {field("college", "College or university", { autoComplete: "organization" }, true)}
          </>
        ) : (
          <>
            {field("contact_person", "Your name", { autoComplete: "name" })}
            {field("company_name", "Company or organisation", { autoComplete: "organization" }, true)}
          </>
        )}
        {field("email", "Email", { type: "email", autoComplete: "email" })}
        <Field label="Password" error={errors.password} hint="At least 8 characters.">
          {(id, describedBy) => (
            <PasswordInput
              id={id}
              autoComplete="new-password"
              value={values.password}
              onChange={set("password")}
              aria-invalid={!!errors.password}
              aria-describedby={describedBy}
            />
          )}
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={pending}>
          Create {role === "STUDENT" ? "student" : "client"} account
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-fg underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense>
      <RegisterForm />
    </Suspense>
  );
}
