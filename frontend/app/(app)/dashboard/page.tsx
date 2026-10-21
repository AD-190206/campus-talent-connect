"use client";

import { useUser } from "@/lib/auth";
import { AdminDashboard } from "./admin";
import { ClientDashboard } from "./client";
import { StudentDashboard } from "./student";

export default function DashboardPage() {
  const user = useUser();
  if (user.role === "STUDENT") return <StudentDashboard />;
  if (user.role === "CLIENT") return <ClientDashboard />;
  return <AdminDashboard />;
}
