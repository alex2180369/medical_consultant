import { useEffect, useState } from "react";

import {
  UsageEvent,
  UsageSummary,
  WalletInfo,
  WalletTransaction,
  getUsageEvents,
  getUsageSummary,
  getWallet,
  getWalletTransactions
} from "../api";

const REASON_LABELS: Record<string, string> = {
  welcome_bonus: "Стартовый бонус",
  admin_top_up: "Пополнение администратором"
};

function formatReason(reason: string): string {
  return REASON_LABELS[reason] ?? reason;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("ru-RU");
}

export function AccountBillingPanel() {
  const [wallet, setWallet] = useState<WalletInfo | null>(null);
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [transactions, setTransactions] = useState<WalletTransaction[]>([]);
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void Promise.all([
      getWallet(),
      getUsageSummary(),
      getWalletTransactions(10),
      getUsageEvents(15)
    ])
      .then(([walletInfo, usageSummary, walletTransactions, usageEvents]) => {
        setWallet(walletInfo);
        setSummary(usageSummary);
        setTransactions(walletTransactions);
        setEvents(usageEvents);
      })
      .catch((loadError) => {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Не удалось загрузить данные учёта."
        );
      });
  }, []);

  if (error) {
    return <div className="auth-error">{error}</div>;
  }

  if (!wallet || !summary) {
    return <p className="muted">Загрузка данных учёта...</p>;
  }

  return (
    <div className="account-billing">
      <div className="settings-block billing-balance-card">
        <h3>Баланс</h3>
        <p className="billing-balance-value">💎 {wallet.credits_balance} кредитов</p>
        <p className="muted">
          Бесплатных ходов при нулевом балансе: {wallet.free_turns_remaining}
        </p>
      </div>

      <div className="settings-block">
        <h3>Курс и оплата</h3>
        <p>
          <strong>Курс:</strong> 1 ₽ = {wallet.credits_per_rub} кредитов
        </p>
        <p>
          <strong>Стартовый бонус:</strong> {wallet.starter_credits} кредитов
          после одобрения регистрации
        </p>
        <p className="muted">
          Онлайн-оплата: {wallet.payment_gateway_status === "coming_soon"
            ? "скоро будет доступна"
            : wallet.payment_gateway_status}
        </p>
        <p className="muted billing-note">{summary.note}</p>
      </div>

      <div className="settings-block">
        <h3>Расход за всё время</h3>
        <p>
          Списано: <strong>{summary.total_charged_credits}</strong> кредитов
        </p>
        <p className="muted">
          Оценочная стоимость запросов: {summary.total_estimated_credits} кредитов
        </p>
        <p className="muted">Токенов обработано: {summary.total_tokens}</p>
      </div>

      <div className="settings-block">
        <h3>История пополнений</h3>
        {transactions.length === 0 ? (
          <p className="muted">Пополнений пока не было.</p>
        ) : (
          <ul className="billing-list">
            {transactions.map((item) => (
              <li key={item.id}>
                <strong>{item.delta_credits > 0 ? "+" : ""}{item.delta_credits} 💎</strong>
                {" — "}
                {formatReason(item.reason)}
                <span className="muted"> · {formatDate(item.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="settings-block">
        <h3>Последние операции ИИ</h3>
        {events.length === 0 ? (
          <p className="muted">Запросов к моделям пока не было.</p>
        ) : (
          <ul className="billing-list">
            {events.map((item) => (
              <li key={item.id}>
                <strong>{item.operation_type}</strong>
                {" · "}
                {item.charged_credits > 0
                  ? `−${item.charged_credits} 💎`
                  : item.is_charged
                    ? "0 💎"
                    : "бесплатный ход"}
                <span className="muted">
                  {" "}
                  · {item.model} · {formatDate(item.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
