import { FormEvent, useEffect, useState } from "react";

import { deleteAccount, logout } from "../api";
import { AccountBillingPanel } from "./AccountBillingPanel";

type SettingsTab = "profile" | "billing";

type SettingsPageProps = {
  email: string;
  name: string;
  initialTab?: SettingsTab;
  paymentReturnOrderId?: string | null;
  onPaymentReturnHandled?: () => void;
  onPrivacy: () => void;
  onAbout: () => void;
  onLegal: () => void;
  onLogout: () => void;
  onDeleted: () => void;
};

export function SettingsPage({
  email,
  name,
  initialTab = "profile",
  paymentReturnOrderId = null,
  onPaymentReturnHandled,
  onPrivacy,
  onAbout,
  onLegal,
  onLogout,
  onDeleted
}: SettingsPageProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>(initialTab);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

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
      <h2>Аккаунт</h2>

      <div className="settings-tabs">
        <button
          type="button"
          className={activeTab === "profile" ? "settings-tab is-active" : "settings-tab"}
          onClick={() => setActiveTab("profile")}
        >
          Профиль
        </button>
        <button
          type="button"
          className={activeTab === "billing" ? "settings-tab is-active" : "settings-tab"}
          onClick={() => setActiveTab("billing")}
        >
          Учёт
        </button>
      </div>

      {activeTab === "billing" ? (
        <AccountBillingPanel
          paymentReturnOrderId={paymentReturnOrderId}
          onPaymentReturnHandled={onPaymentReturnHandled}
        />
      ) : (
        <>
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
        </>
      )}
    </section>
  );
}
