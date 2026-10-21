import { RoleGate } from "@/components/role-gate";
import { PageHeader } from "@/components/ui/layout";
import { Unavailable } from "@/components/unavailable";

export const metadata = { title: "Disputes" };

export default function DisputesPage() {
  return (
    <RoleGate allow={["ADMIN"]}>
      <PageHeader title="Disputes" description="Complaints and disputes raised by students and clients." />
      <Unavailable
        title="Dispute management isn’t available yet"
        description="No service records complaints or disputes yet, so there is nothing to review here. Payment refunds also have no API endpoint."
        needs={["POST /api/disputes/", "GET /api/disputes/", "POST /api/disputes/{dispute_id}/resolve/", "POST /api/payments/{payment_id}/refund/"]}
      />
    </RoleGate>
  );
}
