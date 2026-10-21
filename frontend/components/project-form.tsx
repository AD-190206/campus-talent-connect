"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api";
import type { ProjectInput } from "@/lib/types";
import { Button } from "./ui/button";
import { Alert } from "./ui/feedback";
import { Field, Input, Textarea, TagInput } from "./ui/field";

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function validateProject(v: ProjectInput) {
  const errors: Record<string, string> = {};
  if (v.title.trim().length < 5) errors.title = "Use a descriptive title of at least 5 characters.";
  if (v.title.length > 200) errors.title = "Keep the title under 200 characters.";
  if (v.description.trim().length < 20) errors.description = "Describe the work in at least 20 characters.";
  const budget = Number(v.budget);
  if (!v.budget || !Number.isFinite(budget) || budget <= 0) errors.budget = "Enter a budget greater than zero.";
  else if (!/^\d{1,10}(\.\d{1,2})?$/.test(v.budget)) errors.budget = "Use at most two decimal places.";
  if (!v.deadline) errors.deadline = "Choose a deadline.";
  else if (v.deadline < today()) errors.deadline = "The deadline can’t be in the past.";
  return errors;
}

interface ProjectFormProps {
  initial?: ProjectInput;
  submitLabel: string;
  /** Optional second action, e.g. "Save and publish". */
  secondary?: { label: string; onSubmit: (values: ProjectInput) => Promise<void> };
  onSubmit: (values: ProjectInput) => Promise<void>;
  onCancel: () => void;
}

export function ProjectForm({ initial, submitLabel, secondary, onSubmit, onCancel }: ProjectFormProps) {
  const [values, setValues] = useState<ProjectInput>(
    initial ?? { title: "", description: "", skills: [], category: "", budget: "", deadline: "" }
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState<"primary" | "secondary" | null>(null);

  const set = <K extends keyof ProjectInput>(key: K, value: ProjectInput[K]) =>
    setValues((v) => ({ ...v, [key]: value }));

  const run = async (which: "primary" | "secondary") => {
    const clean = { ...values, title: values.title.trim(), description: values.description.trim(), category: values.category.trim() };
    const nextErrors = validateProject(clean);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setPending(which);
    setFormError(null);
    try {
      await (which === "primary" ? onSubmit : secondary!.onSubmit)(clean);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) {
        setErrors(err.fieldErrors);
        setFormError("Please fix the highlighted fields.");
      } else {
        setFormError(err instanceof ApiError ? err.message : "The project could not be saved.");
      }
      setPending(null);
    }
  };

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        run("primary");
      }}
      className="card divide-y divide-line"
    >
      <div className="space-y-5 p-5 sm:p-6">
        {formError && <Alert>{formError}</Alert>}
        <Field label="Project title" error={errors.title}>
          {(id, d) => (
            <Input
              id={id}
              value={values.title}
              onChange={(e) => set("title", e.target.value)}
              placeholder="e.g. Build a booking page for a campus society"
              aria-invalid={!!errors.title}
              aria-describedby={d}
              maxLength={200}
            />
          )}
        </Field>
        <Field
          label="Description"
          error={errors.description}
          hint="What needs to be built, what you’ll provide, and how you’ll judge the result."
        >
          {(id, d) => (
            <Textarea
              id={id}
              value={values.description}
              onChange={(e) => set("description", e.target.value)}
              rows={7}
              aria-invalid={!!errors.description}
              aria-describedby={d}
            />
          )}
        </Field>
        <Field label="Required skills" error={errors.skills} hint="Press Enter or comma after each skill." optional>
          {(id, d) => (
            <TagInput
              id={id}
              value={values.skills}
              onChange={(skills) => set("skills", skills)}
              placeholder="React, Figma, Python…"
              describedBy={d}
              invalid={!!errors.skills}
            />
          )}
        </Field>
        <div className="grid gap-5 sm:grid-cols-3">
          <Field label="Category" error={errors.category} optional>
            {(id, d) => (
              <Input
                id={id}
                value={values.category}
                onChange={(e) => set("category", e.target.value)}
                placeholder="e.g. Web"
                aria-describedby={d}
              />
            )}
          </Field>
          <Field label="Budget (₹)" error={errors.budget} hint="The amount the student is paid.">
            {(id, d) => (
              <Input
                id={id}
                value={values.budget}
                onChange={(e) => set("budget", e.target.value.replace(/[^\d.]/g, ""))}
                inputMode="decimal"
                placeholder="5000"
                aria-invalid={!!errors.budget}
                aria-describedby={d}
              />
            )}
          </Field>
          <Field label="Deadline" error={errors.deadline}>
            {(id, d) => (
              <Input
                id={id}
                type="date"
                min={today()}
                value={values.deadline}
                onChange={(e) => set("deadline", e.target.value)}
                aria-invalid={!!errors.deadline}
                aria-describedby={d}
              />
            )}
          </Field>
        </div>
      </div>
      <div className="flex flex-col-reverse gap-2 p-4 sm:flex-row sm:justify-end sm:px-6">
        <Button variant="ghost" onClick={onCancel} disabled={!!pending}>
          Cancel
        </Button>
        {secondary && (
          <Button variant="secondary" onClick={() => run("secondary")} loading={pending === "secondary"} disabled={!!pending}>
            {secondary.label}
          </Button>
        )}
        <Button type="submit" loading={pending === "primary"} disabled={!!pending}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
