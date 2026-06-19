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

export async function uploadDocument(
  file: File,
  description: string
): Promise<DocumentRecord> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("description", description);

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
