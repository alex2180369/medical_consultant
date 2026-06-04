import { FormEvent, useState } from "react";

import { LoginRequest, UserCreate, createUser, login } from "../api";

type LoginPageProps = {
  onSuccess: () => void;
};

export function LoginPage({ onSuccess }: LoginPageProps) {
  const [credentials, setCredentials] = useState<LoginRequest>({
    username: "",
    password: ""
  });
  const [newUser, setNewUser] = useState<UserCreate>({
    username: "",
    password: "",
    display_name: ""
  });
  const [showAdminPanel, setShowAdminPanel] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      await login(credentials);
      onSuccess();
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Не удалось войти."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("");
    setError("");

    try {
      await login({ username: "admin", password: "admin" });
      await createUser(newUser);
      setNewUser({ username: "", password: "", display_name: "" });
      setStatus("Пользователь создан. Теперь войдите под его именем.");
      setShowAdminPanel(false);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Не удалось создать пользователя."
      );
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-logo">
          <div className="icon">🩺</div>
          <h1>Медицинский консультант</h1>
          <p>Ваш персональный ИИ-помощник для здоровья семьи</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            Имя пользователя
            <input
              autoComplete="username"
              required
              value={credentials.username}
              onChange={(event) =>
                setCredentials({
                  ...credentials,
                  username: event.target.value
                })
              }
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              autoComplete="current-password"
              required
              value={credentials.password}
              onChange={(event) =>
                setCredentials({
                  ...credentials,
                  password: event.target.value
                })
              }
            />
          </label>
          {error && <div className="login-error">{error}</div>}
          {status && <div className="status-banner">{status}</div>}
          <button type="submit" disabled={isSubmitting} style={{ width: "100%" }}>
            {isSubmitting ? "Вход..." : "Войти в систему"}
          </button>
        </form>

        <button
          className="secondary-button login-admin-toggle"
          type="button"
          onClick={() => setShowAdminPanel(!showAdminPanel)}
        >
          {showAdminPanel ? "Скрыть" : "Добавить пользователя (admin)"}
        </button>

        {showAdminPanel && (
          <form className="login-form login-admin-form" onSubmit={handleCreateUser}>
            <h2>Новый пользователь семьи</h2>
            <label>
              Имя для входа
              <input
                required
                value={newUser.username}
                onChange={(event) =>
                  setNewUser({ ...newUser, username: event.target.value })
                }
              />
            </label>
            <label>
              Отображаемое имя
              <input
                value={newUser.display_name}
                onChange={(event) =>
                  setNewUser({ ...newUser, display_name: event.target.value })
                }
              />
            </label>
            <label>
              Пароль
              <input
                type="password"
                required
                minLength={4}
                value={newUser.password}
                onChange={(event) =>
                  setNewUser({ ...newUser, password: event.target.value })
                }
              />
            </label>
            <button type="submit">Создать пользователя</button>
          </form>
        )}
      </div>
    </div>
  );
}
