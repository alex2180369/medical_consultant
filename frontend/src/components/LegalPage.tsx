import { ReactNode } from "react";

const PRIVACY_POLICY_PDF_URL = "/privacy-policy.pdf";

type LegalPageProps = {
  title: string;
  children: ReactNode;
  onBack: () => void;
};

export function LegalPage({ title, children, onBack }: LegalPageProps) {
  return (
    <section className="panel legal-page">
      <button className="secondary-button" type="button" onClick={onBack}>
        ← Назад
      </button>
      <h2>{title}</h2>
      <div className="legal-content">{children}</div>
    </section>
  );
}

export function PrivacyPolicyContent() {
  return (
    <iframe
      className="legal-pdf-viewer"
      src={PRIVACY_POLICY_PDF_URL}
      title="Политика конфиденциальности"
    />
  );
}

export function AboutAppContent() {
  return (
    <>
      <p>
        Медицинский консультант — информационный ИИ-помощник для семьи. Сервис
        помогает собрать анамнез, проанализировать симптомы, хранить анализы и
        подготовиться к визиту к врачу.
      </p>
      <p>
        Приложение не заменяет очный приём врача и не предназначено для
        экстренной медицинской помощи.
      </p>
    </>
  );
}

export function LegalInfoContent() {
  return (
    <>
      <p>
        Это заглушка раздела «Правовая информация». Здесь будут указаны сведения
        об операторе персональных данных, контакты для обращений пользователей
        и порядок реализации прав субъекта персональных данных.
      </p>
      <p>
        Для удаления аккаунта и всех связанных данных используйте кнопку
        «Удалить аккаунт и данные» в настройках профиля.
      </p>
    </>
  );
}
