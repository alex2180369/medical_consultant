import { getAccessToken, setAccessToken, clearAccessToken } from "./lib/auth";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export type UserPublic = {
  id: string;
  email: string;
  name: string;
};

export type SessionInfo = {
  user: UserPublic;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: UserPublic;
};

export type RegisterResponse = {
  message: string;
};

export type MedicalProfile = {
  full_name: string;
  age: number | null;
  birth_date: string | null;
  sex: string;
  blood_type: string;
  height_cm: number | null;
  weight_kg: number | null;
  diabetes_status: string;
  cardiovascular_status: string;
  chronic_conditions: string;
  allergies: string;
  medications: string;
  family_history: string;
  lifestyle: string;
  activity_level: string;
  smoking_status: string;
  sleep_hours: number | null;
  stress_level: string;
  family_members: number | null;
  notes: string;
};

export type LabResult = {
  id: number;
  marker_name: string;
  value: number;
  unit: string;
  reference_range: string;
  measured_at: string;
  comment: string;
  trend: {
    previous_value: number | null;
    delta: number | null;
    direction: "baseline" | "up" | "down" | "same";
  } | null;
};

export type LabResultCreate = Omit<LabResult, "id" | "trend">;

export type DocumentRecord = {
  id: number;
  filename: string;
  content_type: string;
  path: string;
  description: string;
  extracted_text: string;
  analysis_status: string;
  created_at: string;
};

export type ComplaintCreate = {
  symptoms: string;
  doctor_feedback: string;
  notes: string;
  occurred_at: string;
  analysis_mode?: "standard" | "complex" | "review";
};

export type ComplaintRecord = ComplaintCreate & {
  id: number;
  created_at: string;
  ai_analysis: string;
  ai_diagnosis: string;
  ai_treatment: string;
  ai_doctor_questions: string;
  ai_urgency: string;
  ai_status: string;
  ai_opinion_comparison: string;
};

export type ConsultationChatRequest = {
  consultation_id?: number | null;
  message: string;
  occurred_at?: string;
  doctor_feedback?: string;
  notes?: string;
  force_complex?: boolean;
};

export type ConsultationChatResponse = {
  consultation_id: number;
  reply: string;
  phase: "anamnesis" | "conclusion";
  ai_status: string;
  complaint: ComplaintRecord | null;
  usage: TurnUsageInfo | null;
};

export type TurnUsageInfo = {
  credits_charged: number;
  estimated_credits: number;
  tokens_total: number;
  model: string;
  balance_remaining: number;
  free_turns_remaining: number;
  used_free_turn: boolean;
};

export type WalletInfo = {
  credits_balance: number;
  free_turns_remaining: number;
  credits_per_rub: number;
  starter_credits: number;
  payment_gateway_status: string;
};

export type UsageSummary = {
  total_events: number;
  total_tokens: number;
  total_estimated_credits: number;
  total_charged_credits: number;
  credits_per_rub: number;
  by_operation: Record<string, number>;
  billing_mode: string;
  note: string;
};

export type UsageEvent = {
  id: number;
  operation_type: string;
  llm_task: string | null;
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_credits: number;
  charged_credits: number;
  cache_hit: boolean;
  is_charged: boolean;
  consultation_id: number | null;
  complaint_id: number | null;
  document_id: number | null;
  created_at: string;
};

export type WalletTransaction = {
  id: number;
  delta_credits: number;
  reason: string;
  reference_id: string | null;
  created_at: string;
};

export type TopUpPackage = {
  id: string;
  credits: number;
  amount_rub: number;
  title: string;
};

export type PaymentPackagesInfo = {
  payment_gateway_status: string;
  credits_per_rub: number;
  packages: TopUpPackage[];
};

export type PaymentOrder = {
  id: string;
  package_id: string;
  amount_rub: number;
  credits: number;
  status: string;
  provider: string;
  confirmation_url: string | null;
  created_at: string;
  updated_at: string;
  paid_at: string | null;
};

export type DocumentCostEstimate = {
  estimated_credits: number;
  requires_confirmation: boolean;
  is_billable: boolean;
  analysis_type: string;
  warning_message: string | null;
  page_count: number | null;
  file_size_bytes: number;
  model: string | null;
};

export type ReceiptLine = {
  operation_type: string;
  operation_label: string;
  model: string;
  event_count: number;
  total_tokens: number;
  estimated_credits: number;
  charged_credits: number;
};

export type ConsultationReceipt = {
  consultation_id: number;
  occurred_at: string | null;
  status: string;
  complaint_id: number | null;
  total_tokens: number;
  total_estimated_credits: number;
  total_charged_credits: number;
  free_turns_used: number;
  lines: ReceiptLine[];
  generated_at: string;
};

export type NutritionPlanResponse = {
  ai_status: "completed" | "no_api_key" | "failed";
  message: string;
  menu: unknown[];
};

async function buildHeaders(options?: RequestInit): Promise<Headers> {
  const headers = new Headers(options?.headers);
  if (!headers.has("Content-Type") && options?.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  return headers;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = await buildHeaders(options);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      } else if (Array.isArray(payload.detail)) {
        detail = payload.detail
          .map((item) => {
            if (typeof item === "object" && item && "msg" in item) {
              return String(item.msg);
            }
            return String(item);
          })
          .join("; ");
      }
    } catch {
      // Keep generic HTTP status when response body is not JSON.
    }

    if (response.status === 504) {
      throw new Error(
        "Сервер долго ждёт ответ модели. Попробуйте ещё раз или отключите «Сложный случай»."
      );
    }

    if (response.status === 402) {
      throw new Error(
        detail ||
          "Недостаточно кредитов. Пополните баланс в разделе «Настройки → Учёт»."
      );
    }

    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function getSession(): Promise<SessionInfo> {
  return request<SessionInfo>("/api/auth/me");
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const response = await request<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
  setAccessToken(response.access_token);
  return response;
}

export async function register(
  name: string,
  email: string,
  password: string,
  consent: boolean
): Promise<RegisterResponse> {
  return request<RegisterResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ name, email, password, consent })
  });
}

export function forgotPassword(email: string): Promise<{ message: string }> {
  return request<{ message: string }>("/api/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email })
  });
}

export function resetPassword(
  token: string,
  password: string
): Promise<{ message: string }> {
  return request<{ message: string }>("/api/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, password })
  });
}

export function logout(): void {
  clearAccessToken();
}

export function deleteAccount(): Promise<void> {
  return request<void>("/api/account", {
    method: "DELETE",
    body: JSON.stringify({ confirm: true })
  });
}

export function getWallet(): Promise<WalletInfo> {
  return request<WalletInfo>("/api/account/wallet");
}

export function getUsageSummary(): Promise<UsageSummary> {
  return request<UsageSummary>("/api/account/usage/summary");
}

export function getUsageEvents(limit = 20): Promise<UsageEvent[]> {
  return request<UsageEvent[]>(`/api/account/usage/events?limit=${limit}`);
}

export function getWalletTransactions(limit = 10): Promise<WalletTransaction[]> {
  return request<WalletTransaction[]>(
    `/api/account/wallet/transactions?limit=${limit}`
  );
}

export function getPaymentPackages(): Promise<PaymentPackagesInfo> {
  return request<PaymentPackagesInfo>("/api/account/payments/packages");
}

export function createPayment(packageId: string): Promise<PaymentOrder> {
  return request<PaymentOrder>("/api/account/payments", {
    method: "POST",
    body: JSON.stringify({ package_id: packageId })
  });
}

export function getPaymentOrder(orderId: string): Promise<PaymentOrder> {
  return request<PaymentOrder>(`/api/account/payments/${orderId}`);
}

export function getProfile(): Promise<MedicalProfile> {
  return request<MedicalProfile>("/api/profile");
}

export function saveProfile(profile: MedicalProfile): Promise<MedicalProfile> {
  return request<MedicalProfile>("/api/profile", {
    method: "PUT",
    body: JSON.stringify(profile)
  });
}

export function listLabs(): Promise<LabResult[]> {
  return request<LabResult[]>("/api/labs");
}

export function createLab(payload: LabResultCreate): Promise<LabResult> {
  return request<LabResult>("/api/labs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listComplaints(): Promise<ComplaintRecord[]> {
  return request<ComplaintRecord[]>("/api/complaints");
}

export function compareOpinions(
  id: number,
  doctorFeedback: string
): Promise<ComplaintRecord> {
  return request<ComplaintRecord>(`/api/complaints/${id}/compare-opinions`, {
    method: "POST",
    body: JSON.stringify({ doctor_feedback: doctorFeedback })
  });
}

export function sendConsultationChat(
  payload: ConsultationChatRequest
): Promise<ConsultationChatResponse> {
  return request<ConsultationChatResponse>("/api/consultations/chat", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function generateNutritionMenu(
  pantryItems: string[],
  includeMedicalRecommendations: boolean
): Promise<NutritionPlanResponse> {
  return request<NutritionPlanResponse>("/api/nutrition/weekly-menu", {
    method: "POST",
    body: JSON.stringify({
      pantry_items: pantryItems,
      include_medical_recommendations: includeMedicalRecommendations
    })
  });
}

export function listDocuments(): Promise<DocumentRecord[]> {
  return request<DocumentRecord[]>("/api/documents");
}

export function deleteDocument(documentId: number): Promise<void> {
  return request<void>(`/api/documents/${documentId}`, {
    method: "DELETE"
  });
}

export async function estimateDocumentCost(file: File): Promise<DocumentCostEstimate> {
  const formData = new FormData();
  formData.append("file", file);

  const headers = await buildHeaders();
  headers.delete("Content-Type");

  const response = await fetch(`${API_BASE_URL}/api/documents/estimate`, {
    method: "POST",
    headers,
    body: formData
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // Keep generic HTTP status when response body is not JSON.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<DocumentCostEstimate>;
}

export async function uploadDocument(
  file: File,
  description: string,
  confirmHighCost = false
): Promise<DocumentRecord> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("description", description);
  if (confirmHighCost) {
    formData.append("confirm_high_cost", "true");
  }

  const headers = await buildHeaders();
  headers.delete("Content-Type");

  const response = await fetch(`${API_BASE_URL}/api/documents`, {
    method: "POST",
    headers,
    body: formData
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // Keep generic HTTP status when response body is not JSON.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<DocumentRecord>;
}

export function getConsultationReceipt(
  consultationId: number
): Promise<ConsultationReceipt> {
  return request<ConsultationReceipt>(`/api/consultations/${consultationId}/receipt`);
}

export function getComplaintReceipt(complaintId: number): Promise<ConsultationReceipt> {
  return request<ConsultationReceipt>(`/api/complaints/${complaintId}/receipt`);
}
