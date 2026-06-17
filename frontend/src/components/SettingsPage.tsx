import { FormEvent, useState } from "react";

import { deleteAccount, logout } from "../api";

type SettingsPageProps = {
  email: string;
  name: string;
  onPrivacy: () => void;
  onAbout: () => void;
  onLegal: () => void;
  onLogout: () => void;
  onDeleted: () => void;
};

export function SettingsPage({
  email,
  name,
  onPrivacy,
  onAbout,
  onLegal,
  onLogout,
  onDeleted
}: SettingsPageProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  async function handleDelete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!confirmDelete) {
      setError("Подтвердите удаление аккаунта.");
      return;
    }

    setError("");
    setStatus("");
    setIsDeleting(true);

    try {
      await deleteAccount();
      logout();
      onDeleted();
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : "Не удалось удалить аккаунт."
      );
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <section className="panel settings-page">
      <h2>Настройки</h2>

      <div className="settings-block">
        <h3>Профиль</h3>
        <p>
          <strong>Имя:</strong> {name || "—"}
        </p>
        <p>
          <strong>Email:</strong> {email || "—"}
        </p>
      </div>

      <div className="settings-block">
        <h3>Правовая информация</h3>
        <div className="settings-links">
          <button type="button" className="secondary-button" onClick={onPrivacy}>
            Политика конфиденциальности
          </button>
          <button type="button" className="secondary-button" onClick={onAbout}>
            О приложении
          </button>
          <button type="button" className="secondary-button" onClick={onLegal}>
            Правовая информация
          </button>
        </div>
      </div>

      <div className="settings-block">
        <h3>Сессия</h3>
        <button type="button" className="secondary-button" onClick={onLogout}>
          Выйти
        </button>
      </div>

      <form className="settings-block settings-danger" onSubmit={handleDelete}>
        <h3>Удаление аккаунта</h3>
        <p className="muted">
          Все ваши данные будут безвозвратно удалены из базы данных.
        </p>
        <label className="auth-consent">
          <input
            type="checkbox"
            checked={confirmDelete}
            onChange={(event) => setConfirmDelete(event.target.checked)}
          />
          <span>Я понимаю, что удаление необратимо</span>
        </label>
        {error && <div className="auth-error">{error}</div>}
        {status && <div className="auth-success">{status}</div>}
        <button
          className="auth-button auth-button-danger"
          type="submit"
          disabled={isDeleting}
        >
          {isDeleting ? "Удаление..." : "Удалить аккаунт и данные"}
        </button>
      </form>
    </section>
  );
}
