import { FormEvent, useState } from "react";

import { register } from "../../api";
import { AuthLayout } from "./AuthLayout";

type RegisterPageProps = {
  onSuccess: () => void;
  onLogin: () => void;
  onPrivacy: () => void;
};

export function RegisterPage({
  onSuccess,
  onLogin,
  onPrivacy
}: RegisterPageProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canSubmit = consent && password.length >= 8 && !isSubmitting;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!consent) {
      setError("Необходимо дать согласие на обработку персональных данных.");
      return;
    }

    setError("");
    setIsSubmitting(true);

    try {
      await register(name.trim(), email.trim(), password, consent);
      onSuccess();
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Не удалось зарегистрироваться."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="auth-field">
          <span>Имя</span>
          <input
            required
            placeholder="Ваше имя"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>

        <label className="auth-field">
          <span>Электронная почта</span>
          <input
            type="email"
            autoComplete="email"
            required
            placeholder="Ваш адрес электронной почты"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <label className="auth-field">
          <span>Пароль</span>
          <div className="auth-password-wrap">
            <input
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              minLength={8}
              placeholder="Ваш пароль"
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
          <small className="auth-hint">
            ℹ Пароль должен содержать не менее 8 символов
          </small>
        </label>

        <label className="auth-consent">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
          />
          <span>
            Я даю согласие на обработку моих персональных данных, включая
            сведения о здоровье, в соответствии с{" "}
            <button
              type="button"
              className="auth-inline-link"
              onClick={onPrivacy}
            >
              Политикой конфиденциальности
            </button>
            .
          </span>
        </label>

        {error && <div className="auth-error">{error}</div>}

        <button
          className={`auth-button ${canSubmit ? "auth-button-primary" : "auth-button-disabled"}`}
          type="submit"
          disabled={!canSubmit}
        >
          {isSubmitting ? "Регистрация..." : "Регистрация"}
        </button>
      </form>

      <p className="auth-footer-text">
        У вас уже есть аккаунт?{" "}
        <button type="button" className="auth-inline-link" onClick={onLogin}>
          Войдите
        </button>
      </p>
    </AuthLayout>
  );
}
