// ─────────────────────────────────────────────────────────────
// INDUS ROUTE — API client
// All calls hit the Next.js proxy `/api/*` -> FastAPI backend
// (see next.config.mjs). Token lives in localStorage.
// ─────────────────────────────────────────────────────────────
export type User = {
  id: string;
  name: string;
  phone: string;
  email?: string;
  role: "applicant" | "officer" | "admin" | "consultant";
};

export type Health = {
  status: string;
  database: string;
  scheduler: string;
  ai_layer: string;
  sms_gateway: string;
  pii_protection: string;
  green_channel_enabled: boolean;
  demo_mode: boolean;
};

const TOKEN_KEY = "sih26130_token";
const USER_KEY = "sih26130_user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export function getUser(): User | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function setUser(user: User | null) {
  if (typeof window === "undefined") return;
  if (user) window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  else window.localStorage.removeItem(USER_KEY);
}

export function logout() {
  setToken(null);
  setUser(null);
}

export function isAuthed(): boolean {
  return typeof window !== "undefined" && !!getToken();
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  if (options.body && typeof options.body === "string") {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch("/api" + path, { ...options, headers });
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const message =
      (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data as T;
}

export const api = {
  get: <T = any>(path: string) => request<T>(path),
  post: <T = any>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T = any>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
};

// ── Auth ──────────────────────────────────────────────────────
export function doLogin(identifier: string, password: string) {
  return api.post<{ token: string; user: User }>("/auth/login", { identifier, password });
}
export function doRegister(payload: {
  name: string; phone: string; email?: string; password: string; role: string; invite_code?: string;
}) {
  return api.post<{ token: string; user: User }>("/auth/register", payload);
}

// ── Profiles ──────────────────────────────────────────────────
export function getMyProfile() {
  return api.get<{ profile: any; checklist: Checklist; ai_summary: any }>("/profiles/me");
}
export function saveProfile(payload: Record<string, any>) {
  return api.post<{ profile_id: string; updated: boolean; pii: any }>("/profiles", payload);
}
export function getSectors() {
  return api.get<{ sectors: { sector: string; label: string }[] }>("/sectors");
}

// ── Applications ──────────────────────────────────────────────
export function listApplications() {
  return api.get<{ applications: AppRow[] }>("/applications");
}
export function createApplication(approvalId: string) {
  return api.post<{ application_id: string }>("/applications", { approval_id: approvalId });
}
export function getApplication(id: string) {
  return api.get<any>(`/applications/${id}`);
}
export function submitApplication(id: string) {
  return api.post<any>(`/applications/${id}/submit`);
}
export function respondClarification(applicationId: string, clarificationId: string, response: string) {
  return api.post<any>(`/applications/${applicationId}/clarifications/${clarificationId}/respond`, { response });
}
export function raiseGrievance(payload: { reason: string; description: string; application_id?: string }) {
  return api.post<{ grievance_id: string; status: string }>("/grievances", payload);
}
export function getMyGrievances() {
  return api.get<{ grievances: any[] }>("/grievances");
}
export function getSchemeRecommendations() {
  return api.get<{ eligible: any[]; others: any[]; note: string }>("/schemes/recommendations");
}
export function askRegulatoryQuestion(q: string) {
  return api.get<any>(`/qa/ask?q=${encodeURIComponent(q)}`);
}
export function getNotifications() {
  return api.get<{ notifications: any[] }>("/notifications");
}
export function getReadiness(applicationId: string) {
  return api.get<any>(`/applications/${applicationId}/readiness`);
}

// ── Officer ────────────────────────────────────────────────────
export function getOfficerQueue() {
  return api.get<{ assigned: any[]; unassigned: any[]; note: string }>("/officer/queue");
}
export function assignApplication(applicationId: string) {
  return api.post<any>(`/officer/applications/${applicationId}/assign`);
}
export function getPreScrutiny(applicationId: string) {
  return api.get<any>(`/officer/applications/${applicationId}/pre-scrutiny`);
}
export function draftClarification(applicationId: string) {
  return api.post<any>(`/officer/applications/${applicationId}/draft-clarification`);
}
export function officerDecision(applicationId: string, action: string, notes?: string, clarificationText?: string) {
  return api.post<any>(`/officer/applications/${applicationId}/decision`, {
    action, notes: notes || "", clarification_text: clarificationText || "",
  });
}
export function scheduleInspection(applicationId: string, date: string, coordinatedWith: string[] = []) {
  return api.post<any>(`/officer/applications/${applicationId}/schedule-inspection`, {
    type: "routine", scheduled_date: date, coordinated_with: coordinatedWith,
  });
}
export function getGreenChannelStatus() {
  return api.get<{ enabled: boolean; rate_limit_per_day: number }>("/officer/green-channel/status");
}

// ── Admin ──────────────────────────────────────────────────────
export function getAdminAnalytics() {
  return api.get<any>("/admin/analytics/summary");
}
export function getAuditLog(limit: number = 100) {
  return api.get<any>(`/admin/audit-log?limit=${limit}`);
}
export function toggleGreenChannel(enabled: boolean) {
  return api.post<{ enabled: boolean }>("/admin/green-channel/toggle", { enabled });
}
export function getAdminUsers() {
  return api.get<{ users: any[] }>("/admin/users");
}

export async function uploadDocument(
  applicationId: string,
  docType: string,
  file: File,
  extractedFields: Record<string, string>
) {
  const form = new FormData();
  form.append("application_id", applicationId);
  form.append("doc_type", docType);
  form.append("file", file);
  form.append("extracted_fields_json", JSON.stringify(extractedFields));
  const token = getToken();
  const res = await fetch("/api/documents/upload", {
    method: "POST",
    headers: token ? { Authorization: "Bearer " + token } : {},
    body: form,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail || "Upload failed");
  return data;
}

// ── DigiLocker e-KYC auto-fill ────────────────────────────────
export function startDigiLocker(aadhaarNumber: string) {
  return api.post<{ consent_id: string; aadhaar_masked: string; demo_otp: string | null; mode: string }>(
    "/digilocker/consent", { aadhaar_number: aadhaarNumber });
}
export function verifyDigiLocker(consentId: string, otp: string) {
  return api.post<{ status: string; verified: any }>(
    `/digilocker/consent/${consentId}/verify`, { otp });
}
export function applyDigiLocker(consentId: string, payload: { pan?: string; gst?: string; authorized_person?: string }) {
  return api.post<{ status: string; verified_identity: any; updated_fields: any }>(
    `/digilocker/consent/${consentId}/apply`, payload);
}
export function digiLockerStatus() {
  return api.get<{ kyc_verified: boolean; identity?: any }>("/digilocker/status");
}

// ── Unified auto-generated application form (PDF) ─────────────
export function generateForm(applicationId: string) {
  return api.post<{ form_id: string; filename: string; verification_code: string; sha256: string; kyc_bound: boolean; size_bytes: number }>(
    `/applications/${applicationId}/generate-form`);
}
export function submitWithForm(applicationId: string) {
  return api.post<{ form_verification_code: string; dispatched: string }>(
    `/applications/${applicationId}/submit-form`);
}
export async function downloadFormPdf(applicationId: string) {
  const token = getToken();
  const res = await fetch(`/api/applications/${applicationId}/form.pdf`,
    { headers: token ? { Authorization: "Bearer " + token } : {} });
  if (!res.ok) throw new Error("Form not available yet");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `IndusRoute-Application-Form-${applicationId.slice(-8)}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Officer instant-queue polling ─────────────────────────────
export function getQueueVersion() {
  return api.get<{ version: string }>("/officer/queue/version");
}

// ── Document specs + parameter sign-offs ──────────────────────
export function getDocumentSpecs() {
  return api.get<{ specs: { doc_type: string; label: string; extractable_fields: string[] }[] }>(
    "/documents/specs");
}
export function signParameter(applicationId: string, paramKey: string, note = "") {
  return api.post<{ signed: boolean; label: string; remaining_parameters: string[]; all_signed: boolean }>(
    `/officer/applications/${applicationId}/sign-parameter`,
    { param_key: paramKey, note });
}

export function health(): Promise<Health> {
  return api.get<Health>("/health");
}
// ── Shared formatting helpers ─────────────────────────────────
export function shortId(id: string | undefined | null, n = 8): string {
  return id ? id.slice(-n) : "—";
}

export function fmtNumber(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "0";
  return new Intl.NumberFormat("en-IN").format(n);
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
    });
  } catch {
    return "—";
  }
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export const DOC_LABELS: Record<string, string> = {
  pan_card: "PAN Card",
  gst_certificate: "GST Registration Certificate",
  lease_deed: "Lease / MIDC Allotment Deed",
  factory_layout: "Factory Layout Plan",
  self_declaration: "Self-Declaration (Statutory Form)",
};

export const STATUS_META: Record<
  string,
  { short: string; color: "black" | "red" | "amber" }
> = {
  draft: { short: "DRAFT", color: "black" },
  submitted: { short: "SUBMITTED", color: "black" },
  under_review: { short: "IN REVIEW", color: "black" },
  clarification_pending: { short: "CLARIFICATION", color: "amber" },
  approved: { short: "APPROVED", color: "black" },
  rejected: { short: "REJECTED", color: "red" },
  provisionally_cleared: { short: "PROVISIONAL", color: "black" },
};

// Type helpers for backend payloads
export type ChecklistApproval = {
  id: string;
  code: string;
  name: string;
  department: string;
  description: string;
  sla_days: number;
  required_documents: string[];
  dependency_ids: string[];
  parallel_group: string;
  green_channel_eligible: boolean;
};

export type Checklist = {
  known: boolean;
  sector: string;
  approvals: ChecklistApproval[];
  excluded: { id: string; code: string; name: string; reason: string }[];
  parallel_groups: Record<string, string[]>;
  max_sla_days: number;
  total_sla_days: number;
  note: string;
};

export type AppRow = {
  id: string;
  status: string;
  approval_id: string;
  approval_name: string;
  approval_code: string;
  department: string;
  sla_days: number;
  submitted_at: string | null;
  sla_deadline: string | null;
  assigned_officer_id: string | null;
  decision_source: string;
  readiness_score: number | null;
  green_channel: number | boolean;
  provisional_certificate: any;
  sla: { state: string; remaining_hours: number | null; deadline: string | null };
  created_at: string;
};