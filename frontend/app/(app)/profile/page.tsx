"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ExternalLink, GraduationCap, Mail, MessageSquare, Pencil, Phone } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { ROLE_LABEL, useUser } from "@/lib/auth";
import { initials, relativeTime, splitSkills } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { ClientProfile, Profile, StudentProfile } from "@/lib/types";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Alert, EmptyState, ErrorState, SkeletonRows } from "@/components/ui/feedback";
import { Field, Input, TagInput } from "@/components/ui/field";
import { PageHeader, Section } from "@/components/ui/layout";
import { SkillTag } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { Stars } from "@/components/ui/stars";

const isStudent = (p: Profile): p is StudentProfile => "college" in p;

function StudentForm({ profile, onSave }: { profile: StudentProfile; onSave: (p: Partial<StudentProfile>) => Promise<void> }) {
  const [v, setV] = useState({ ...profile, skillList: splitSkills(profile.skills) });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!v.name.trim()) next.name = "Your name is required.";
    if (v.portfolio_url && !/^https?:\/\/\S+$/.test(v.portfolio_url.trim())) next.portfolio_url = "Enter a full URL starting with https://";
    if (v.phone && !/^[+\d\s()-]{6,20}$/.test(v.phone.trim())) next.phone = "Enter a valid phone number.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setPending(true);
    try {
      await onSave({
        name: v.name.trim(),
        college: v.college.trim(),
        phone: v.phone.trim(),
        portfolio_url: v.portfolio_url.trim(),
        skills: v.skillList.join(", "),
      });
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors);
    } finally {
      setPending(false);
    }
  };

  return (
    <form onSubmit={save} noValidate className="space-y-4 p-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name" error={errors.name}>
          {(id, d) => <Input id={id} value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} aria-describedby={d} aria-invalid={!!errors.name} />}
        </Field>
        <Field label="College" error={errors.college} optional>
          {(id, d) => <Input id={id} value={v.college} onChange={(e) => setV({ ...v, college: e.target.value })} aria-describedby={d} />}
        </Field>
        <Field label="Phone" error={errors.phone} optional>
          {(id, d) => <Input id={id} type="tel" value={v.phone} onChange={(e) => setV({ ...v, phone: e.target.value })} aria-describedby={d} aria-invalid={!!errors.phone} />}
        </Field>
        <Field label="Portfolio link" error={errors.portfolio_url} optional>
          {(id, d) => <Input id={id} type="url" placeholder="https://" value={v.portfolio_url} onChange={(e) => setV({ ...v, portfolio_url: e.target.value })} aria-describedby={d} aria-invalid={!!errors.portfolio_url} />}
        </Field>
      </div>
      <Field label="Skills" hint="Press Enter or comma after each skill." error={errors.skills}>
        {(id, d) => <TagInput id={id} value={v.skillList} onChange={(skillList) => setV({ ...v, skillList })} placeholder="Python, React, UI design…" describedBy={d} />}
      </Field>
      <Button type="submit" loading={pending}>
        Save profile
      </Button>
    </form>
  );
}

function ClientForm({ profile, onSave }: { profile: ClientProfile; onSave: (p: Partial<ClientProfile>) => Promise<void> }) {
  const [v, setV] = useState(profile);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!v.contact_person.trim()) next.contact_person = "A contact name is required.";
    if (v.phone && !/^[+\d\s()-]{6,20}$/.test(v.phone.trim())) next.phone = "Enter a valid phone number.";
    setErrors(next);
    if (Object.keys(next).length) return;
    setPending(true);
    try {
      await onSave({ contact_person: v.contact_person.trim(), company_name: v.company_name.trim(), phone: v.phone.trim() });
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fieldErrors);
    } finally {
      setPending(false);
    }
  };

  return (
    <form onSubmit={save} noValidate className="space-y-4 p-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Contact name" error={errors.contact_person}>
          {(id, d) => <Input id={id} value={v.contact_person} onChange={(e) => setV({ ...v, contact_person: e.target.value })} aria-describedby={d} aria-invalid={!!errors.contact_person} />}
        </Field>
        <Field label="Company or organisation" error={errors.company_name} optional>
          {(id, d) => <Input id={id} value={v.company_name} onChange={(e) => setV({ ...v, company_name: e.target.value })} aria-describedby={d} />}
        </Field>
        <Field label="Phone" error={errors.phone} optional>
          {(id, d) => <Input id={id} type="tel" value={v.phone} onChange={(e) => setV({ ...v, phone: e.target.value })} aria-describedby={d} aria-invalid={!!errors.phone} />}
        </Field>
      </div>
      <Button type="submit" loading={pending}>
        Save profile
      </Button>
    </form>
  );
}

function ProfileInner() {
  const user = useUser();
  const toast = useToast();
  const params = useSearchParams();
  const profile = useResource(() => api.users.profile(user.user_id), [user.user_id]);
  const reviews = useResource(() => api.reviews.list({ page_size: 100 }), []);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (params.get("welcome")) setEditing(true);
  }, [params]);

  const p = profile.data?.data;
  const received = (reviews.data?.data ?? []).filter((r) => r.reviewee_id === user.user_id);
  const average = received.length ? received.reduce((s, r) => s + r.rating, 0) / received.length : null;

  const save = async (patch: Partial<StudentProfile> | Partial<ClientProfile>) => {
    try {
      await api.users.updateProfile(user.user_id, patch);
      toast("Profile saved.");
      setEditing(false);
      profile.reload();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Profile could not be saved.", "error");
      throw err;
    }
  };

  if (profile.error) return <ErrorState error={profile.error} onRetry={profile.reload} />;
  if (!p) return <SkeletonRows rows={2} />;

  const name = isStudent(p) ? p.name : p.contact_person;
  const subtitle = isStudent(p) ? p.college : p.company_name;
  const skills = isStudent(p) ? splitSkills(p.skills) : [];

  return (
    <>
      <PageHeader title="Profile" description="How you appear to others on Campus Talent Connect." />
      {params.get("welcome") && (
        <Alert tone="success" className="mb-6" title="Welcome to Campus Talent Connect">
          Add your skills and a portfolio link so clients can see what you’re good at.
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-6">
          <section className="card p-5 sm:p-6">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
              <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-accent text-xl font-semibold text-accent-fg">
                {initials(name || user.email)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold">{name || "Unnamed"}</h2>
                    <p className="text-sm text-muted">
                      {ROLE_LABEL[user.role]}
                      {subtitle && ` · ${subtitle}`}
                    </p>
                  </div>
                  {!editing && (
                    <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
                      <Pencil className="h-3.5 w-3.5" aria-hidden />
                      Edit
                    </Button>
                  )}
                </div>
                <ul className="mt-4 space-y-1.5 text-sm text-muted">
                  <li className="flex items-center gap-2">
                    <Mail className="h-4 w-4" aria-hidden />
                    {user.email}
                  </li>
                  {p.phone && (
                    <li className="flex items-center gap-2">
                      <Phone className="h-4 w-4" aria-hidden />
                      {p.phone}
                    </li>
                  )}
                  {isStudent(p) && p.college && (
                    <li className="flex items-center gap-2">
                      <GraduationCap className="h-4 w-4" aria-hidden />
                      {p.college}
                    </li>
                  )}
                  {isStudent(p) && p.portfolio_url && (
                    <li>
                      <a
                        href={p.portfolio_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-2 font-medium text-primary hover:underline"
                      >
                        <ExternalLink className="h-4 w-4" aria-hidden />
                        Portfolio
                      </a>
                    </li>
                  )}
                </ul>
                {isStudent(p) && (
                  <div className="mt-5">
                    <p className="label-caps">Skills</p>
                    {skills.length ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {skills.map((s) => (
                          <SkillTag key={s}>{s}</SkillTag>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-2 text-sm text-muted">No skills added yet.</p>
                    )}
                  </div>
                )}
              </div>
            </div>
          </section>

          {editing && (
            <Section
              title="Edit profile"
              actions={
                <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              }
            >
              {isStudent(p) ? <StudentForm profile={p} onSave={save} /> : <ClientForm profile={p as ClientProfile} onSave={save} />}
            </Section>
          )}

          <Section title="Reviews received">
            {received.length ? (
              <ul className="divide-y divide-line">
                {received.map((r) => (
                  <li key={r.id} className="px-5 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <Stars rating={r.rating} />
                      <span className="text-xs text-muted">{relativeTime(r.created_at)}</span>
                    </div>
                    {r.comment && <p className="mt-2 text-sm text-muted">{r.comment}</p>}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={MessageSquare}
                title="No reviews yet"
                description="Reviews appear after completed assignments."
              />
            )}
          </Section>
        </div>

        <aside>
          <section className="card p-5">
            <p className="label-caps">Rating</p>
            {average !== null ? (
              <>
                <p className="mt-2 text-3xl font-semibold tabular-nums">{average.toFixed(1)}</p>
                <Stars rating={Math.round(average)} className="mt-1" />
                <p className="mt-2 text-[13px] text-muted">
                  From {received.length} review{received.length === 1 ? "" : "s"}
                </p>
              </>
            ) : (
              <p className="mt-2 text-sm text-muted">Not rated yet.</p>
            )}
          </section>
        </aside>
      </div>
    </>
  );
}

export default function ProfilePage() {
  return (
    <RoleGate allow={["STUDENT", "CLIENT"]}>
      <Suspense>
        <ProfileInner />
      </Suspense>
    </RoleGate>
  );
}
