"use client";

import Link from "next/link";
import { useState } from "react";
import { CircleCheck, FlaskConical, Hourglass, Receipt, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { formatDate, formatMoney, sumMoney } from "@/lib/format";
import { fetchAssignment, fetchProject, useResource } from "@/lib/hooks";
import type { Payment, PaymentStatus } from "@/lib/types";
import { RoleGate } from "@/components/role-gate";
import { Alert, EmptyState, ErrorState, Skeleton, SkeletonRows } from "@/components/ui/feedback";
import { PageHeader, Pager, StatCard, Tabs } from "@/components/ui/layout";
import { StatusBadge } from "@/components/ui/status-badge";

/** Resolve "payment → assignment → project" titles for display. */
function usePaymentTitles(payments: Payment[]) {
  const key = payments.map((p) => p.assignment_id).join(",");
  return useResource(
    async () => {
      const entries = await Promise.all(
        payments.map(async (p) => {
          const assignment = await fetchAssignment(p.assignment_id);
          const project = assignment ? await fetchProject(assignment.project_id) : null;
          return [p.assignment_id, project?.title ?? null] as const;
        })
      );
      return Object.fromEntries(entries) as Record<string, string | null>;
    },
    [key],
    payments.length > 0
  );
}

export default function PaymentsPage() {
  const user = useUser();
  const student = user.role === "STUDENT";
  const [status, setStatus] = useState<"" | PaymentStatus>("");
  const [page, setPage] = useState(1);
  const result = useResource(() => api.payments.list({ status, page, page_size: 20 }), [status, page]);
  // Totals come from the full history, independent of the current tab.
  const all = useResource(() => api.payments.list({ page_size: 100 }), []);
  const titles = usePaymentTitles(result.data?.data ?? []);

  const mine = (all.data?.data ?? []).filter((p) => (student ? p.payee_id : p.payer_id) === user.user_id);
  const released = sumMoney(mine.filter((p) => p.status === "RELEASED").map((p) => (student ? p.net_amount : p.amount)));
  const held = sumMoney(mine.filter((p) => p.status === "SUCCESS").map((p) => (student ? p.net_amount : p.amount)));
  const stat = (v: React.ReactNode) => (all.loading ? <Skeleton className="h-7 w-20" /> : all.error ? "—" : v);

  return (
    <RoleGate allow={["STUDENT", "CLIENT"]}>
      <PageHeader
        title={student ? "Earnings" : "Payments"}
        description={student ? "Payments for your completed and funded work." : "Payments you’ve made to students."}
      />

      <Alert tone="info" className="mb-6">
        <span className="flex gap-2">
          <FlaskConical className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>
            Payments run through a <strong>development mock gateway</strong>. Statuses and references are real records
            in the platform, but no money is transferred.
          </span>
        </span>
      </Alert>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label={student ? "Received" : "Released to students"}
          icon={CircleCheck}
          value={stat(formatMoney(released))}
        />
        <StatCard
          label={student ? "Funded, awaiting approval" : "Funded, not yet released"}
          icon={Hourglass}
          value={stat(formatMoney(held))}
        />
        <StatCard label="Payments" icon={Receipt} value={stat(mine.length)} />
      </div>

      <div className="mt-8">
        <Tabs
          label="Filter by status"
          value={status}
          onChange={(v) => {
            setStatus(v);
            setPage(1);
          }}
          options={[
            { value: "", label: "All" },
            { value: "RELEASED", label: "Released" },
            { value: "SUCCESS", label: "Funded" },
            { value: "PENDING", label: "Pending" },
            { value: "FAILED", label: "Failed" },
          ]}
        />
        <div className="mt-4">
          {result.error ? (
            <ErrorState error={result.error} onRetry={result.reload} />
          ) : result.loading ? (
            <SkeletonRows rows={3} />
          ) : result.data?.data.length ? (
            <>
              <div className="card overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-[13px] text-muted">
                      <th scope="col" className="px-5 py-3 font-medium">Project</th>
                      <th scope="col" className="px-5 py-3 font-medium">Date</th>
                      <th scope="col" className="px-5 py-3 font-medium">Reference</th>
                      <th scope="col" className="px-5 py-3 text-right font-medium">{student ? "You receive" : "Amount"}</th>
                      <th scope="col" className="px-5 py-3 text-right font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {result.data.data.map((p) => (
                      <tr key={p.id} className="hover:bg-surface-2/50">
                        <td className="px-5 py-3.5">
                          <Link href={`/assignments/${p.assignment_id}`} className="font-medium hover:underline">
                            {titles.data?.[p.assignment_id] ?? "Assignment"}
                          </Link>
                        </td>
                        <td className="px-5 py-3.5 text-muted">{formatDate(p.created_at)}</td>
                        <td className="px-5 py-3.5 font-mono text-xs text-muted">{p.transaction_id ?? "—"}</td>
                        <td className="px-5 py-3.5 text-right font-medium tabular-nums">
                          {formatMoney(student ? p.net_amount : p.amount)}
                        </td>
                        <td className="px-5 py-3.5 text-right">
                          <StatusBadge status={p.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager pagination={result.data.pagination} onPage={setPage} />
            </>
          ) : (
            <div className="card">
              <EmptyState
                icon={Wallet}
                title={status ? "No payments with this status" : "No payments yet"}
                description={
                  student
                    ? "Payments appear once a client funds or approves your work."
                    : "Fund an assignment or approve submitted work to create a payment."
                }
              />
            </div>
          )}
        </div>
      </div>
    </RoleGate>
  );
}
