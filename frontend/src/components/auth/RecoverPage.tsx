import { FormEvent, useState } from "react";

import { recoverPassword } from "../../lib/appwrite";
import { AuthLayout } from "./AuthLayout";

type RecoverPageProps = {
  onLogin: () => void;
  onRegister: () => void;
};

export function RecoverPage({ onLogin, onRegister }: RecoverPageProps) {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    setIsSubmitting(true);

    try {
      await recoverPassword(email.trim());
      setMessage("Письмо для восстановления пароля отправлено на вашу почту.");
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Не удалось отправить письмо."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <h1 className="auth-title">Восстановление пароля</h1>

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

        {error && <div className="auth-error">{error}</div>}
        {message && <div className="auth-success">{message}</div>}

        <button
          className="auth-button auth-button-primary"
          type="submit"
          disabled={isSubmitting}
        >
          {isSubmitting ? "Отправка..." : "Восстановить"}
        </button>
      </form>

      <div className="auth-links">
        <button type="button" onClick={onLogin}>
          Вход
        </button>
        <span>|</span>
        <button type="button" onClick={onRegister}>
          Регистрация
        </button>
      </div>
    </AuthLayout>
  );
}
