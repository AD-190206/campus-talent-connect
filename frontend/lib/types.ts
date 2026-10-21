// Shapes returned by the gateway, per docs/api/API_CONTRACT.md.
// IDs are UUID strings, money is a decimal string, timestamps are ISO 8601.

export type Role = "STUDENT" | "CLIENT" | "ADMIN";

export interface Envelope<T> {
  data: T;
  message: string;
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface Collection<T> extends Envelope<T[]> {
  pagination: Pagination;
}

export interface ErrorEnvelope {
  error: string;
  code: string;
  details: { fields?: Record<string, string[] | string> } & Record<string, unknown>;
}

export interface SessionUser {
  user_id: string;
  email: string;
  role: Role;
}

export interface Tokens {
  access_token: string;
  refresh_token: string;
  token_type: "Bearer";
  expires_in: number;
  user?: SessionUser;
}

export interface UserAccount extends SessionUser {
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface StudentProfile {
  name: string;
  phone: string;
  college: string;
  skills: string;
  portfolio_url: string;
  rating: number;
}

export interface ClientProfile {
  company_name: string;
  contact_person: string;
  phone: string;
}

export type Profile = StudentProfile | ClientProfile;

export type ProjectStatus =
  | "DRAFT"
  | "PUBLISHED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "CLOSED"
  | "ARCHIVED";

export interface Project {
  id: string;
  client_id: string;
  title: string;
  description: string;
  skills: string[];
  category: string;
  budget: string;
  deadline: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export type ProjectInput = Pick<
  Project,
  "title" | "description" | "skills" | "category" | "budget" | "deadline"
>;

export type ApplicationStatus =
  | "submitted"
  | "shortlisted"
  | "selected"
  | "rejected"
  | "withdrawn";

export interface Application {
  id: string;
  student_id: string;
  project_id: string;
  proposal: string;
  resume_url: string;
  status: ApplicationStatus;
  created_at: string;
  updated_at: string;
}

export type AssignmentStatus = "active" | "completed" | "cancelled";

export interface Assignment {
  id: string;
  application_id: string;
  student_id: string;
  client_id: string;
  project_id: string;
  status: AssignmentStatus;
  assigned_date: string;
  completion_date: string | null;
}

export type WorkStatus = "DRAFT" | "SUBMITTED" | "REVISION_REQUESTED" | "APPROVED";

export interface Work {
  id: string;
  assignment_id: string;
  student_id: string;
  project_id: string;
  title: string;
  description: string;
  submission_url: string;
  status: WorkStatus;
  feedback: string;
  submitted_at: string | null;
  reviewed_at: string | null;
  payment_requested: boolean;
  created_at: string;
  updated_at: string;
}

export interface Review {
  id: string;
  assignment_id: string;
  reviewer_id: string;
  reviewee_id: string;
  reviewer_role: "STUDENT" | "CLIENT";
  rating: number;
  comment: string;
  created_at: string;
}

export type PaymentStatus =
  | "PENDING"
  | "PROCESSING"
  | "SUCCESS"
  | "FAILED"
  | "REFUNDED"
  | "RELEASED";

export interface Payment {
  id: string;
  assignment_id: string;
  payer_id: string;
  payee_id: string;
  amount: string;
  fee: string;
  net_amount: string;
  payment_mode: "MOCK" | string;
  status: PaymentStatus;
  transaction_id: string | null;
  idempotency_key: string;
  created_at: string;
  updated_at: string;
}

export interface Notification {
  id: string;
  user_id: string;
  type: "IN_APP" | "EMAIL" | "SMS";
  event: string;
  message: string;
  is_read: boolean;
  created_at: string;
}
