"use client";

import { useState } from "react";
import { FlaskConical, Wallet } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { formatDateTime, formatMoney } from "@/lib/format";
import { useResource } from "@/lib/hooks";
import type { Assignment, Payment, Project } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { ErrorState, Skeleton } from "@/components/ui/feedback";
import { Section } from "@/components/ui/layout";
import { Badge, StatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";

const INACTIVE = ["FAILED", "REFUNDED"];

function newKey(assignmentId: string) {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now());
  return `fund-${assignmentId}-${random}`;
}

function explain(payment: Payment | undefined, role: string, completed: boolean) {
  if (!payment)
    return role === "CLIENT"
      ? completed
        ? "No payment record exists for this assignment."
        : "Fund the assignment now, or approval will create and process the payment automatically."
      : "The client hasn’t funded this assignment yet. Payment is processed when your work is approved.";
  switch (payment.status) {
    case "PENDING":
    case "PROCESSING":
      return "The payment has been created but not processed yet.";
    case "SUCCESS":
      return role === "CLIENT"
        ? "Funded. It will be released to the student when you approve the work."
        : "Funded by the client. It’s released to you when your work is approved.";
    case "RELEASED":
      return role === "CLIENT" ? "Released to the student." : "Released to you.";
    case "FAILED":
      return "The last payment attempt failed.";
    default:
      return "";
  }
}

export function PaymentPanel({
  assignment,
  project,
  refreshKey,
}: {
  assignment: Assignment;
  project: Project | null;
  refreshKey: number;
}) {
  const user = useUser();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [processing, setProcessing] = useState(false);
  const payments = useResource(
    () => api.payments.list({ assignment_id: assignment.id, page_size: 20 }),
    [assignment.id, refreshKey]
  );

  const list = payments.data?.data ?? [];
  const payment = list.find((p) => !INACTIVE.includes(p.status)) ?? list[0];
  const client = user.role === "CLIENT";
  const canFund = client && assignment.status === "active" && (!payment || INACTIVE.includes(payment.status));
  const canProcess = client && payment && (payment.status === "PENDING" || payment.status === "PROCESSING");

  const process = async (p: Payment) => {
    setProcessing(true);
    try {
      const { data } = await api.payments.process(p.id);
      toast(data.status === "SUCCESS" ? "Payment processed by the mock gateway." : `Payment ${data.status.toLowerCase()}.`,
        data.status === "SUCCESS" ? "success" : "error");
      payments.reload();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Processing failed.", "error");
    } finally {
      setProcessing(false);
    }
  };

  return (
    <Section
      title="Payment"
      actions={
        <Badge tone="neutral" className="gap-1">
          <FlaskConical className="h-3 w-3" aria-hidden />
          Mock gateway
        </Badge>
      }
    >
      {payments.error ? (
        <ErrorState error={payments.error} onRetry={payments.reload} className="m-4 border-0 px-2 py-6" />
      ) : payments.loading ? (
        <div className="space-y-3 p-5">
          <Skeleton className="h-6 w-1/2" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      ) : (
        <div className="p-5">
          {payment ? (
            <>
              <div className="flex items-center justify-between gap-3">
                <p className="text-2xl font-semibold tabular-nums">{formatMoney(payment.amount)}</p>
                <StatusBadge status={payment.status} />
              </div>
              <dl className="mt-4 space-y-2 text-[13px]">
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">Platform fee</dt>
                  <dd className="tabular-nums">{formatMoney(payment.fee)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">Student receives</dt>
                  <dd className="font-medium tabular-nums">{formatMoney(payment.net_amount)}</dd>
                </div>
                {payment.transaction_id && (
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted">Reference</dt>
                    <dd className="truncate font-mono text-xs">{payment.transaction_id}</dd>
                  </div>
                )}
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">Updated</dt>
                  <dd>{formatDateTime(payment.updated_at)}</dd>
                </div>
              </dl>
            </>
          ) : (
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 text-muted">
                <Wallet className="h-4 w-4" aria-hidden />
              </span>
              <p className="text-sm font-medium">Not funded yet</p>
            </div>
          )}
          <p className="mt-4 text-[13px] leading-relaxed text-muted">
            {explain(payment, user.role, assignment.status === "completed")}
          </p>
          {canProcess && (
            <Button className="mt-4 w-full" variant="secondary" onClick={() => process(payment!)} loading={processing}>
              Process payment
            </Button>
          )}
          {canFund && (
            <Button className="mt-4 w-full" variant="secondary" onClick={() => setConfirm(true)}>
              Fund assignment
            </Button>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Fund this assignment?"
        description={
          <>
            A payment for the project budget
            {project ? (
              <>
                {" "}
                of <strong className="text-fg">{formatMoney(project.budget)}</strong>
              </>
            ) : null}{" "}
            is created and processed by the <strong className="text-fg">development mock gateway</strong>. No real money
            moves. Funds are released to the student only when you approve their work.
          </>
        }
        confirmLabel="Fund with mock payment"
        onConfirm={async () => {
          const { data } = await api.payments.create({
            assignment_id: assignment.id,
            payee_id: assignment.student_id,
            idempotency_key: newKey(assignment.id),
          });
          const processed = await api.payments.process(data.id);
          toast(
            processed.data.status === "SUCCESS" ? "Assignment funded (mock payment)." : "The mock payment did not succeed.",
            processed.data.status === "SUCCESS" ? "success" : "error"
          );
          payments.reload();
        }}
      />
    </Section>
  );
}
