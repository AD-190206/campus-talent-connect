import { RoleGate } from "@/components/role-gate";
import { PageHeader } from "@/components/ui/layout";
import { Unavailable } from "@/components/unavailable";

export const metadata = { title: "Verification" };

export default function VerificationPage() {
  return (
    <RoleGate allow={["ADMIN"]}>
      <PageHeader title="Verification" description="Confirm student status and review new project listings." />
      <Unavailable
        title="Verification isn’t available yet"
        description="Student and project verification needs a verification status on accounts and projects, and endpoints to review it. Neither the User nor the Project service provides these yet."
        needs={["GET /api/users/?verified=false", "POST /api/users/{user_id}/verify/", "POST /api/projects/{project_id}/verify/"]}
      />
    </RoleGate>
  );
}
