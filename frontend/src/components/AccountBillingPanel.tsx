import { useEffect, useState } from "react";

import {
  PaymentOrder,
  PaymentPackagesInfo,
  UsageEvent,
  UsageSummary,
  WalletInfo,
  WalletTransaction,
  createPayment,
  getPaymentOrder,
  getPaymentPackages,
  getUsageEvents,
  getUsageSummary,
  getWallet,
  getWalletTransactions
} from "../api";

const REASON_LABELS: Record<string, string> = {
  welcome_bonus: "Стартовый бонус",
  admin_top_up: "Пополнение администратором",
  payment_top_up: "Онлайн-оплата"
};

type AccountBillingPanelProps = {
  paymentReturnOrderId?: string | null;
  onPaymentReturnHandled?: () => void;
};

function formatReason(reason: string): string {
  return REASON_LABELS[reason] ?? reason;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("ru-RU");
}

function formatRub(value: number): string {
  return value.toLocaleString("ru-RU", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2
  });
}

export function AccountBillingPanel({
  paymentReturnOrderId = null,
  onPaymentReturnHandled
}: AccountBillingPanelProps) {
  const [wallet, setWallet] = useState<WalletInfo | null>(null);
  const [packagesInfo, setPackagesInfo] = useState<PaymentPackagesInfo | null>(null);
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [transactions, setTransactions] = useState<WalletTransaction[]>([]);
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [payingPackageId, setPayingPackageId] = useState<string | null>(null);

  async function reloadBillingData() {
    const [walletInfo, paymentPackages, usageSummary, walletTransactions, usageEvents] =
      await Promise.all([
        getWallet(),
        getPaymentPackages(),
        getUsageSummary(),
        getWalletTransactions(10),
        getUsageEvents(15)
      ]);

    setWallet(walletInfo);
    setPackagesInfo(paymentPackages);
    setSummary(usageSummary);
    setTransactions(walletTransactions);
    setEvents(usageEvents);
  }

  useEffect(() => {
    void reloadBillingData().catch((loadError) => {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Не удалось загрузить данные учёта."
      );
    });
  }, []);

  useEffect(() => {
    if (typeof paymentReturnOrderId !== "string" || paymentReturnOrderId.length === 0) {
      return;
    }

    const trackedOrderId = paymentReturnOrderId;
    let attempts = 0;
    const maxAttempts = 8;

    async function pollPaymentStatus() {
      try {
        const order: PaymentOrder = await getPaymentOrder(trackedOrderId);
        if (order.status === "succeeded") {
          setStatus(`Оплата прошла успешно. На баланс зачислено ${order.credits} 💎.`);
          await reloadBillingData();
          onPaymentReturnHandled?.();
          return;
        }

        if (order.status === "canceled") {
          setStatus("Оплата отменена.");
          onPaymentReturnHandled?.();
          return;
        }

        attempts += 1;
        if (attempts < maxAttempts) {
          window.setTimeout(() => {
            void pollPaymentStatus();
          }, 2000);
          return;
        }

        setStatus(
          "Платёж ещё обрабатывается. Баланс обновится автоматически после подтверждения."
        );
        onPaymentReturnHandled?.();
      } catch (pollError) {
        setError(
          pollError instanceof Error
            ? pollError.message
            : "Не удалось проверить статус оплаты."
        );
        onPaymentReturnHandled?.();
      }
    }

    void pollPaymentStatus();
  }, [paymentReturnOrderId, onPaymentReturnHandled]);

  async function handleTopUp(packageId: string) {
    setError("");
    setStatus("");
    setPayingPackageId(packageId);

    try {
      const order = await createPayment(packageId);
      if (!order.confirmation_url) {
        throw new Error("Платёжный провайдер не вернул ссылку для оплаты.");
      }
      window.location.href = order.confirmation_url;
    } catch (payError) {
      setError(
        payError instanceof Error
          ? payError.message
          : "Не удалось создать платёж."
      );
      setPayingPackageId(null);
    }
  }

  if (error && !wallet) {
    return <div className="auth-error">{error}</div>;
  }

  if (!wallet || !summary || !packagesInfo) {
    return <p className="muted">Загрузка данных учёта...</p>;
  }

  const paymentsEnabled = packagesInfo.payment_gateway_status === "enabled";

  return (
    <div className="account-billing">
      {status && <div className="billing-status">{status}</div>}
      {error && <div className="auth-error">{error}</div>}

      <div className="settings-block billing-balance-card">
        <h3>Баланс</h3>
        <p className="billing-balance-value">💎 {wallet.credits_balance} кредитов</p>
        <p className="muted">
          Бесплатных ходов при нулевом балансе: {wallet.free_turns_remaining}
        </p>
      </div>

      <div className="settings-block">
        <h3>Пополнение баланса</h3>
        <p className="muted">
          Курс: 1 ₽ = {packagesInfo.credits_per_rub} кредитов.
          {paymentsEnabled
            ? " Выберите пакет и перейдите на защищённую страницу оплаты YooKassa."
            : " Онлайн-оплата скоро будет доступна — пока баланс можно пополнить через администратора."}
        </p>
        <div className="billing-top-up-grid">
          {packagesInfo.packages.map((item) => (
            <button
              key={item.id}
              type="button"
              className={
                paymentsEnabled
                  ? "billing-top-up-card"
                  : "billing-top-up-card billing-top-up-card-disabled"
              }
              disabled={!paymentsEnabled || payingPackageId !== null}
              onClick={() => void handleTopUp(item.id)}
            >
              <strong>{item.title}</strong>
              <span>{formatRub(item.amount_rub)} ₽</span>
              <span className="muted">
                {!paymentsEnabled
                  ? "Скоро"
                  : payingPackageId === item.id
                    ? "Переход к оплате..."
                    : "Оплатить"}
              </span>
            </button>
          ))}
        </div>
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
          Онлайн-оплата:{" "}
          {paymentsEnabled
            ? "доступна"
            : wallet.payment_gateway_status === "coming_soon"
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
                <strong>
                  {item.delta_credits > 0 ? "+" : ""}
                  {item.delta_credits} 💎
                </strong>
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
