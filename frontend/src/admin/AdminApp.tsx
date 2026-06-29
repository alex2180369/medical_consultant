import { FormEvent, useEffect, useState } from "react";

import {
  AdminUserRecord,
  BlockedEmailRecord,
  adminLogin,
  adminLogout,
  approveApplication,
  disableUser,
  getUserWallet,
  listApplications,
  listApprovedUsers,
  listBlockedEmails,
  rejectApplication,
  topUpUserWallet
} from "./api";
import { getAccessToken } from "../lib/auth";
import "../styles.css";
import "./admin.css";

type AdminTab = "applications" | "users" | "blocked";

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString("ru-RU");
}

function AdminLogin({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      await adminLogin(email.trim(), password);
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
    <div className="admin-shell">
      <section className="admin-panel admin-login-panel">
        <h1>Администрирование</h1>
        <p>Вход только для администратора проекта.</p>
        <form className="admin-form" onSubmit={handleSubmit}>
          <label>
            <span>Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            <span>Пароль</span>
            <input
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error && <div className="admin-error">{error}</div>}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Вход..." : "Войти"}
          </button>
        </form>
      </section>
    </div>
  );
}

function ApplicationCard({
  item,
  onUpdated
}: {
  item: AdminUserRecord;
  onUpdated: () => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  async function handleApprove() {
    setError("");
    setIsBusy(true);
    try {
      await approveApplication(item.id);
      onUpdated();
    } catch (actionError) {
      setError(
        actionError instanceof Error
          ? actionError.message
          : "Не удалось одобрить заявку."
      );
    } finally {
      setIsBusy(false);
    }
  }

  async function handleReject() {
    setError("");
    setIsBusy(true);
    try {
      await rejectApplication(item.id, reason.trim());
      onUpdated();
    } catch (actionError) {
      setError(
        actionError instanceof Error
          ? actionError.message
          : "Не удалось отклонить заявку."
      );
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <article className="admin-card">
      <header>
        <strong>{item.name || "Без имени"}</strong>
        <span>{item.email}</span>
      </header>
      <p>
        <span>Дата заявки:</span> {formatDate(item.created_at)}
      </p>
      {item.ai_suggested_name && (
        <p>
          <span>AI-ФИО:</span> {item.ai_suggested_name}
          {item.ai_confidence ? ` (${item.ai_confidence})` : ""}
        </p>
      )}
      {item.ai_email_analysis && (
        <p className="admin-analysis">{item.ai_email_analysis}</p>
      )}
      <label>
        <span>Причина отклонения (необязательно)</span>
        <input
          type="text"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Комментарий для себя"
        />
      </label>
      {error && <div className="admin-error">{error}</div>}
      <div className="admin-actions">
        <button type="button" onClick={handleApprove} disabled={isBusy}>
          Принять
        </button>
        <button
          type="button"
          className="admin-button-danger"
          onClick={handleReject}
          disabled={isBusy}
        >
          Отклонить
        </button>
      </div>
    </article>
  );
}

function UserCard({
  item,
  onUpdated
}: {
  item: AdminUserRecord;
  onUpdated: () => void;
}) {
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [walletBalance, setWalletBalance] = useState<number | null>(null);
  const [topUpCredits, setTopUpCredits] = useState("100");
  const [topUpNote, setTopUpNote] = useState("");
  const [topUpStatus, setTopUpStatus] = useState("");

  useEffect(() => {
    void getUserWallet(item.id)
      .then((wallet) => setWalletBalance(wallet.credits_balance))
      .catch(() => setWalletBalance(null));
  }, [item.id]);

  async function handleTopUp() {
    const credits = Number(topUpCredits);
    if (!Number.isFinite(credits) || credits <= 0) {
      setError("Введите положительное число кредитов.");
      return;
    }

    setError("");
    setTopUpStatus("");
    setIsBusy(true);
    try {
      const wallet = await topUpUserWallet(item.id, credits, topUpNote.trim());
      setWalletBalance(wallet.credits_balance);
      setTopUpStatus(`Баланс обновлён: ${wallet.credits_balance} 💎`);
      setTopUpNote("");
    } catch (actionError) {
      setError(
        actionError instanceof Error
          ? actionError.message
          : "Не удалось пополнить баланс."
      );
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDisable() {
    if (
      !window.confirm(
        `Отключить и полностью удалить пользователя ${item.email}?`
      )
    ) {
      return;
    }

    setError("");
    setIsBusy(true);
    try {
      await disableUser(item.id);
      onUpdated();
    } catch (actionError) {
      setError(
        actionError instanceof Error
          ? actionError.message
          : "Не удалось отключить пользователя."
      );
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <article className="admin-card">
      <header>
        <strong>{item.name || "Без имени"}</strong>
        <span>{item.email}</span>
      </header>
      <p>
        <span>Одобрен:</span> {formatDate(item.approved_at)}
      </p>
      {walletBalance !== null && (
        <p>
          <span>Баланс:</span> {walletBalance} 💎
        </p>
      )}
      <div className="admin-top-up-form">
        <label>
          <span>Пополнить кредиты</span>
          <input
            type="number"
            min={1}
            value={topUpCredits}
            onChange={(event) => setTopUpCredits(event.target.value)}
          />
        </label>
        <label>
          <span>Комментарий</span>
          <input
            type="text"
            value={topUpNote}
            onChange={(event) => setTopUpNote(event.target.value)}
            placeholder="Причина пополнения"
          />
        </label>
        <button type="button" onClick={() => void handleTopUp()} disabled={isBusy}>
          Пополнить баланс
        </button>
      </div>
      {topUpStatus && <p className="admin-success">{topUpStatus}</p>}
      {error && <div className="admin-error">{error}</div>}
      <div className="admin-actions">
        <button
          type="button"
          className="admin-button-danger"
          onClick={handleDisable}
          disabled={isBusy}
        >
          Отключить и удалить
        </button>
      </div>
    </article>
  );
}

export function AdminApp() {
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(getAccessToken()));
  const [activeTab, setActiveTab] = useState<AdminTab>("applications");
  const [applications, setApplications] = useState<AdminUserRecord[]>([]);
  const [users, setUsers] = useState<AdminUserRecord[]>([]);
  const [blockedEmails, setBlockedEmails] = useState<BlockedEmailRecord[]>([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function loadData() {
    setError("");
    setIsLoading(true);
    try {
      const [apps, approved, blocked] = await Promise.all([
        listApplications(),
        listApprovedUsers(),
        listBlockedEmails()
      ]);
      setApplications(apps);
      setUsers(approved);
      setBlockedEmails(blocked);
    } catch (loadError) {
      if (loadError instanceof Error && loadError.message.includes("403")) {
        adminLogout();
        setIsAuthenticated(false);
      }
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Не удалось загрузить данные."
      );
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (isAuthenticated) {
      void loadData();
    }
  }, [isAuthenticated]);

  if (!isAuthenticated) {
    return <AdminLogin onSuccess={() => setIsAuthenticated(true)} />;
  }

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <div>
          <h1>Администрирование</h1>
          <p>Модерация заявок и управление пользователями</p>
        </div>
        <div className="admin-header-actions">
          <button type="button" onClick={() => void loadData()} disabled={isLoading}>
            Обновить
          </button>
          <button
            type="button"
            onClick={() => {
              adminLogout();
              setIsAuthenticated(false);
            }}
          >
            Выйти
          </button>
        </div>
      </header>

      <nav className="admin-tabs">
        <button
          type="button"
          className={activeTab === "applications" ? "is-active" : ""}
          onClick={() => setActiveTab("applications")}
        >
          Заявки ({applications.length})
        </button>
        <button
          type="button"
          className={activeTab === "users" ? "is-active" : ""}
          onClick={() => setActiveTab("users")}
        >
          Пользователи ({users.length})
        </button>
        <button
          type="button"
          className={activeTab === "blocked" ? "is-active" : ""}
          onClick={() => setActiveTab("blocked")}
        >
          Заблокированные ({blockedEmails.length})
        </button>
      </nav>

      {error && <div className="admin-error admin-error-banner">{error}</div>}
      {isLoading && <p className="admin-muted">Загрузка...</p>}

      {activeTab === "applications" && (
        <section className="admin-list">
          {applications.length === 0 ? (
            <p className="admin-muted">Нет заявок на рассмотрении.</p>
          ) : (
            applications.map((item) => (
              <ApplicationCard
                key={item.id}
                item={item}
                onUpdated={() => void loadData()}
              />
            ))
          )}
        </section>
      )}

      {activeTab === "users" && (
        <section className="admin-list">
          {users.length === 0 ? (
            <p className="admin-muted">Нет одобренных пользователей.</p>
          ) : (
            users.map((item) => (
              <UserCard
                key={item.id}
                item={item}
                onUpdated={() => void loadData()}
              />
            ))
          )}
        </section>
      )}

      {activeTab === "blocked" && (
        <section className="admin-list">
          {blockedEmails.length === 0 ? (
            <p className="admin-muted">Заблокированных email нет.</p>
          ) : (
            blockedEmails.map((item) => (
              <article className="admin-card" key={item.email}>
                <header>
                  <strong>{item.email}</strong>
                  <span>{item.reason}</span>
                </header>
                <p>
                  <span>Заблокирован:</span> {formatDate(item.blocked_at)}
                </p>
              </article>
            ))
          )}
        </section>
      )}
    </div>
  );
}
