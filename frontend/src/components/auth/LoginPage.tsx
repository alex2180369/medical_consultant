import { FormEvent, useState } from "react";

import { login } from "../../api";
import { AuthLayout } from "./AuthLayout";

type LoginPageProps = {
  onSuccess: () => void;
  onRegister: () => void;
  onRecover: () => void;
};

export function LoginPage({
  onSuccess,
  onRegister,
  onRecover
}: LoginPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      await login(email.trim(), password);
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

  return (
    <AuthLayout>
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="auth-field">
          <span>Электронная почта</span>
          <input
            type="email"
            autoComplete="email"
            required
            placeholder="Электронная почта"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <label className="auth-field">
          <span>Пароль</span>
          <div className="auth-password-wrap">
            <input
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              placeholder="Пароль"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <button
              className="auth-password-toggle"
              type="button"
              aria-label="Показать пароль"
              onClick={() => setShowPassword(!showPassword)}
            >
              👁
            </button>
          </div>
        </label>

        {error && <div className="auth-error">{error}</div>}

        <button
          className="auth-button auth-button-primary"
          type="submit"
          disabled={isSubmitting}
        >
          {isSubmitting ? "Вход..." : "Вход"}
        </button>
      </form>

      <div className="auth-links">
        <button type="button" onClick={onRecover}>
          Забыли пароль?
        </button>
        <span>|</span>
        <button type="button" onClick={onRegister}>
          Зарегистрироваться
        </button>
      </div>
    </AuthLayout>
  );
}
