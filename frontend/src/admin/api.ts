import { getAccessToken, setAccessToken, clearAccessToken } from "../lib/auth";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export type AdminUserRecord = {
  id: string;
  email: string;
  name: string;
  status: string;
  role: string;
  ai_suggested_name: string;
  ai_email_analysis: string;
  ai_confidence: string;
  ai_analyzed_at: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  rejection_reason: string;
  created_at: string | null;
};

export type BlockedEmailRecord = {
  email: string;
  reason: string;
  blocked_at: string;
  blocked_by: string;
};

export type AdminWalletInfo = {
  user_id: string;
  credits_balance: number;
  free_turns_remaining: number;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    email: string;
    name: string;
  };
};

async function adminRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (!headers.has("Content-Type") && options?.body) {
    headers.set("Content-Type", "application/json");
  }

  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Keep generic HTTP status.
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function adminLogin(
  email: string,
  password: string
): Promise<AuthResponse> {
  const response = await adminRequest<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
  setAccessToken(response.access_token);
  return response;
}

export function adminLogout(): void {
  clearAccessToken();
}

export function listApplications(): Promise<AdminUserRecord[]> {
  return adminRequest<AdminUserRecord[]>("/api/admin/applications");
}

export function listApprovedUsers(): Promise<AdminUserRecord[]> {
  return adminRequest<AdminUserRecord[]>("/api/admin/users");
}

export function listBlockedEmails(): Promise<BlockedEmailRecord[]> {
  return adminRequest<BlockedEmailRecord[]>("/api/admin/blocked-emails");
}

export function approveApplication(userId: string): Promise<AdminUserRecord> {
  return adminRequest<AdminUserRecord>(`/api/admin/users/${userId}/approve`, {
    method: "POST"
  });
}

export function rejectApplication(
  userId: string,
  reason: string
): Promise<AdminUserRecord> {
  return adminRequest<AdminUserRecord>(`/api/admin/users/${userId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason })
  });
}

export function disableUser(userId: string): Promise<{ message: string }> {
  return adminRequest<{ message: string }>(`/api/admin/users/${userId}`, {
    method: "DELETE"
  });
}

export function getUserWallet(userId: string): Promise<AdminWalletInfo> {
  return adminRequest<AdminWalletInfo>(`/api/admin/users/${userId}/wallet`);
}

export function topUpUserWallet(
  userId: string,
  credits: number,
  note = ""
): Promise<AdminWalletInfo> {
  return adminRequest<AdminWalletInfo>(`/api/admin/users/${userId}/wallet/top-up`, {
    method: "POST",
    body: JSON.stringify({ credits, note })
  });
}
