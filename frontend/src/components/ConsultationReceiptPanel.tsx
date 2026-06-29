import { useEffect, useState } from "react";

import {
  ConsultationReceipt,
  getComplaintReceipt,
  getConsultationReceipt
} from "../api";

type ConsultationReceiptPanelProps = {
  consultationId?: number | null;
  complaintId?: number | null;
  onClose?: () => void;
};

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString("ru-RU");
}

export function ConsultationReceiptPanel({
  consultationId,
  complaintId,
  onClose
}: ConsultationReceiptPanelProps) {
  const [receipt, setReceipt] = useState<ConsultationReceipt | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError("");

    const loader =
      consultationId != null
        ? getConsultationReceipt(consultationId)
        : complaintId != null
          ? getComplaintReceipt(complaintId)
          : Promise.reject(new Error("Не указана консультация или обращение."));

    void loader
      .then((payload) => {
        setReceipt(payload);
      })
      .catch((loadError) => {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Не удалось загрузить чек."
        );
      })
      .finally(() => {
        setLoading(false);
      });
  }, [consultationId, complaintId]);

  if (loading) {
    return <p className="muted">Загрузка чека...</p>;
  }

  if (error) {
    return <div className="auth-error">{error}</div>;
  }

  if (!receipt) {
    return null;
  }

  return (
    <div className="consultation-receipt">
      <div className="consultation-receipt-header">
        <div>
          <h4>Чек консультации #{receipt.consultation_id}</h4>
          <p className="muted">
            {receipt.occurred_at ? `Дата: ${receipt.occurred_at}` : "Дата не указана"}
            {" · "}
            Сформирован: {formatDate(receipt.generated_at)}
          </p>
        </div>
        {onClose && (
          <button type="button" className="secondary-button" onClick={onClose}>
            Закрыть
          </button>
        )}
      </div>

      <div className="consultation-receipt-totals">
        <p>
          <strong>Списано:</strong> {receipt.total_charged_credits} 💎
        </p>
        <p>
          <strong>Оценочная стоимость:</strong> {receipt.total_estimated_credits} 💎
        </p>
        <p>
          <strong>Токены:</strong> {receipt.total_tokens}
        </p>
        {receipt.free_turns_used > 0 && (
          <p>
            <strong>Бесплатных ходов:</strong> {receipt.free_turns_used}
          </p>
        )}
      </div>

      {receipt.lines.length === 0 ? (
        <p className="muted">По этой консультации пока нет списаний.</p>
      ) : (
        <ul className="billing-list consultation-receipt-lines">
          {receipt.lines.map((line) => (
            <li key={`${line.operation_type}-${line.model}`}>
              <strong>{line.operation_label}</strong>
              <span>
                {line.event_count} × · {line.total_tokens} токенов · списано{" "}
                {line.charged_credits} 💎
                {line.estimated_credits !== line.charged_credits &&
                  ` (оценка ${line.estimated_credits} 💎)`}
              </span>
              <span className="muted">{line.model}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
