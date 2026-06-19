import { FormEvent, useState } from "react";

import { AuthLayout } from "./AuthLayout";

type PendingApprovalPageProps = {
  message: string;
  onLogin: () => void;
};

export function PendingApprovalPage({
  message,
  onLogin
}: PendingApprovalPageProps) {
  return (
    <AuthLayout>
      <div className="auth-form">
        <h2>Заявка отправлена</h2>
        <p>{message}</p>
        <p className="auth-hint">
          После одобрения администратором вы сможете войти в приложение.
        </p>
        <button
          className="auth-button auth-button-primary"
          type="button"
          onClick={onLogin}
        >
          Перейти ко входу
        </button>
      </div>
    </AuthLayout>
  );
}
