"use client";

import { useState } from "react";
import { MessageSquare, Star } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { cn, relativeTime } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { Assignment, Review } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Stars } from "@/components/ui/stars";
import { Alert, EmptyState, ErrorState, Skeleton } from "@/components/ui/feedback";
import { Field, Textarea } from "@/components/ui/field";
import { Section } from "@/components/ui/layout";
import { useToast } from "@/components/ui/toast";

function RatingInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const labels = ["Poor", "Fair", "Good", "Very good", "Excellent"];
  return (
    <div role="radiogroup" aria-label="Rating" className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} – ${labels[n - 1]}`}
          onClick={() => onChange(n)}
          className="rounded-md p-1 hover:bg-surface-2"
        >
          <Star className={cn("h-6 w-6", n <= value ? "fill-warning text-warning" : "text-line-strong")} aria-hidden />
        </button>
      ))}
      {value > 0 && <span className="ml-2 text-sm text-muted">{labels[value - 1]}</span>}
    </div>
  );
}

function ReviewItem({ review, mine }: { review: Review; mine: boolean }) {
  return (
    <li className="px-5 py-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium">{mine ? "Your review" : `From the ${review.reviewer_role.toLowerCase()}`}</p>
        <Stars rating={review.rating} />
      </div>
      {review.comment && <p className="mt-2 whitespace-pre-line text-sm text-muted">{review.comment}</p>}
      <p className="mt-1.5 text-xs text-muted">{relativeTime(review.created_at)}</p>
    </li>
  );
}

export function ReviewPanel({ assignment }: { assignment: Assignment }) {
  const user = useUser();
  const toast = useToast();
  const reviews = useResource(
    () => api.reviews.list({ assignment_id: assignment.id, page_size: 10 }),
    [assignment.id, assignment.status]
  );
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const completed = assignment.status === "completed";
  const list = reviews.data?.data ?? [];
  const mine = list.find((r) => r.reviewer_id === user.user_id);
  const reviewee = user.role === "STUDENT" ? assignment.client_id : assignment.student_id;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rating) {
      setError("Choose a rating from 1 to 5.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await api.reviews.create({
        assignment_id: assignment.id,
        reviewee_id: reviewee,
        rating,
        ...(comment.trim() ? { comment: comment.trim() } : {}),
      });
      toast("Thanks — your review was submitted.");
      reviews.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Your review could not be submitted.");
    } finally {
      setPending(false);
    }
  };

  return (
    <Section
      title="Reviews"
      description={completed ? "Rate your experience on this assignment." : "Available once the work is approved."}
    >
      {reviews.error ? (
        <ErrorState error={reviews.error} onRetry={reviews.reload} className="m-4 border-0" />
      ) : reviews.loading ? (
        <div className="p-5">
          <Skeleton className="h-4 w-1/2" />
        </div>
      ) : (
        <>
          {list.length > 0 && (
            <ul className="divide-y divide-line border-b border-line">
              {list.map((r) => (
                <ReviewItem key={r.id} review={r} mine={r.reviewer_id === user.user_id} />
              ))}
            </ul>
          )}
          {completed && !mine ? (
            <form onSubmit={submit} className="space-y-4 p-5">
              {error && <Alert>{error}</Alert>}
              <div>
                <p className="mb-1.5 text-[13px] font-medium">
                  Rate the {user.role === "STUDENT" ? "client" : "student"}
                </p>
                <RatingInput value={rating} onChange={setRating} />
              </div>
              <Field label="Comment" optional>
                {(id, d) => (
                  <Textarea id={id} rows={3} value={comment} onChange={(e) => setComment(e.target.value)} aria-describedby={d} />
                )}
              </Field>
              <Button type="submit" loading={pending}>
                Submit review
              </Button>
            </form>
          ) : (
            !list.length && (
              <EmptyState
                icon={MessageSquare}
                title="No reviews yet"
                description={
                  completed
                    ? "Reviews from both sides will appear here."
                    : "You can review each other once the client approves the work."
                }
              />
            )
          )}
        </>
      )}
    </Section>
  );
}
