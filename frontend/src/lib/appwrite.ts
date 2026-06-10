import { Account, Client, ID } from "appwrite";

const endpoint =
  import.meta.env.VITE_APPWRITE_ENDPOINT ?? "https://cloud.appwrite.io/v1";
const projectId = import.meta.env.VITE_APPWRITE_PROJECT_ID ?? "";

export const appwriteConfigured = Boolean(projectId);

const client = new Client().setEndpoint(endpoint).setProject(projectId);

export const account = new Account(client);

export async function getAuthJwt(): Promise<string | null> {
  try {
    const jwt = await account.createJWT();
    return jwt.jwt;
  } catch {
    return null;
  }
}

export async function getCurrentUser() {
  return account.get();
}

export async function loginWithEmail(email: string, password: string) {
  await account.createEmailPasswordSession({ email, password });
  return account.get();
}

export async function registerWithEmail(
  name: string,
  email: string,
  password: string
) {
  await account.create({
    userId: ID.unique(),
    email,
    password,
    name
  });
  await account.createEmailPasswordSession({ email, password });
  return account.get();
}

export async function recoverPassword(email: string) {
  const redirectUrl = `${window.location.origin}/`;
  await account.createRecovery({ email, url: redirectUrl });
}

export async function logoutFromAppwrite() {
  await account.deleteSession({ sessionId: "current" });
}
