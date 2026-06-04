import { DragEvent, FormEvent, useEffect, useRef, useState } from "react";

import {
  ComplaintCreate,
  ComplaintRecord,
  LabResult,
  LabResultCreate,
  MedicalProfile,
  SessionInfo,
  UserPublic,
  createLab,
  compareOpinions,
  DocumentRecord,
  getProfile,
  getSession,
  listComplaints,
  listDocuments,
  listLabs,
  listUsers,
  logout,
  saveProfile,
  sendConsultationChat,
  setActAsUserId,
  uploadDocument
} from "./api";
import { LoginPage } from "./components/LoginPage";
import {
  formatAssistantReply,
  OpinionComparisonView
} from "./components/OpinionComparisonView";
import { NutritionPlanner } from "./components/NutritionPlanner";
import "./styles.css";

const emptyProfile: MedicalProfile = {
  full_name: "",
  age: null,
  birth_date: null,
  sex: "",
  blood_type: "",
  height_cm: null,
  weight_kg: null,
  diabetes_status: "",
  cardiovascular_status: "",
  chronic_conditions: "",
  allergies: "",
  medications: "",
  family_history: "",
  lifestyle: "",
  activity_level: "",
  smoking_status: "",
  sleep_hours: null,
  stress_level: "",
  family_members: null,
  notes: ""
};

const emptyLab: LabResultCreate = {
  marker_name: "",
  value: 0,
  unit: "",
  reference_range: "",
  measured_at: new Date().toISOString().slice(0, 10),
  comment: ""
};

const emptyComplaint: ComplaintCreate = {
  symptoms: "",
  doctor_feedback: "",
  notes: "",
  occurred_at: new Date().toISOString().slice(0, 10)
};

const lifestyleSuggestions = [
  "Сидячая работа",
  "Регулярная физическая активность",
  "Курение",
  "Алкоголь редко",
  "Алкоголь регулярно",
  "Недосып",
  "Высокий стресс",
  "Особая диета"
];

const allergyOptions = [
  "🍊 Цитрусовые",
  "🥜 Орехи",
  "🐾 Шерсть",
  "💊 Пенициллин",
  "🌸 Пыльца",
  "🥛 Лактоза",
  "🌾 Глютен",
  "✅ Нет"
];

const bloodTypeOptions = [
  "I (O) Rh+",
  "I (O) Rh−",
  "II (A) Rh+",
  "II (A) Rh−",
  "III (B) Rh+",
  "III (B) Rh−",
  "IV (AB) Rh+",
  "IV (AB) Rh−"
];

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
};

type AppPage =
  | "dashboard"
  | "chat"
  | "questionnaire"
  | "labs"
  | "trends"
  | "history"
  | "nutrition"
  | "fitness";

const CHAT_WELCOME =
  "Здравствуйте! Расскажите о симптомах — я соберу анамнез и сформирую " +
  "первое мнение до визита к врачу. После приёма добавьте мнение врача " +
  "в «Истории обращений», и мы сравним оба варианта.";

const PAGE_TITLES: Record<AppPage, string> = {
  dashboard: "Главная",
  chat: "Чат с ИИ-консультантом",
  questionnaire: "Анкета здоровья",
  labs: "Анализы и снимки",
  trends: "Тренды показателей",
  history: "История обращений",
  nutrition: "ИИ Нутрициолог",
  fitness: "ИИ Фитнес-тренер"
};

function getUserInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return (name.trim()[0] ?? "?").toUpperCase();
}

function formatComplaintTitle(symptoms: string, occurredAt: string): string {
  const short = symptoms.trim().slice(0, 42);
  return short ? (short.length < symptoms.trim().length ? `${short}…` : short) : `Обращение ${occurredAt}`;
}

function createWelcomeMessages(): ChatMessage[] {
  return [{ id: "welcome", role: "assistant", content: CHAT_WELCOME }];
}

function App() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [familyUsers, setFamilyUsers] = useState<UserPublic[]>([]);
  const [authLoading, setAuthLoading] = useState(true);
  const [actAsUserId, setActAsUserIdState] = useState<number | null>(null);

  const [activePage, setActivePage] = useState<AppPage>("dashboard");
  const [isChatHistoryCollapsed, setIsChatHistoryCollapsed] = useState(false);
  const [selectedComplaintId, setSelectedComplaintId] = useState<number | null>(
    null
  );

  const [profile, setProfile] = useState<MedicalProfile>(emptyProfile);
  const [lab, setLab] = useState<LabResultCreate>(emptyLab);
  const [labs, setLabs] = useState<LabResult[]>([]);
  const [complaint, setComplaint] = useState<ComplaintCreate>(emptyComplaint);
  const [complaints, setComplaints] = useState<ComplaintRecord[]>([]);
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [documentDescription, setDocumentDescription] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const documentInputRef = useRef<HTMLInputElement>(null);
  const [isDraggingDocument, setIsDraggingDocument] = useState(false);
  const [isAnalyzingComplaint, setIsAnalyzingComplaint] = useState(false);
  const [isComplaintBranchesOpen, setIsComplaintBranchesOpen] = useState(false);
  const [forceComplexAnalysis, setForceComplexAnalysis] = useState(false);
  const [comparingComplaintId, setComparingComplaintId] = useState<number | null>(
    null
  );
  const [doctorFeedbackDrafts, setDoctorFeedbackDrafts] = useState<
    Record<number, string>
  >({});
  const [consultationId, setConsultationId] = useState<number | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(
    createWelcomeMessages()
  );
  const chatMessagesRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("");

  async function loadWorkspaceData() {
    const [loadedProfile, loadedLabs, loadedComplaints, loadedDocuments] =
      await Promise.all([
        getProfile(),
        listLabs(),
        listComplaints(),
        listDocuments()
      ]);

    setProfile(loadedProfile);
    setLabs(loadedLabs);
    setComplaints(loadedComplaints);
    setDocuments(loadedDocuments);
    setDoctorFeedbackDrafts(
      Object.fromEntries(
        loadedComplaints.map((item) => [item.id, item.doctor_feedback])
      )
    );
  }

  async function bootstrapSession() {
    setAuthLoading(true);
    try {
      const currentSession = await getSession();
      setSession(currentSession);
      const effectiveId = currentSession.effective_user.id;
      setActAsUserIdState(effectiveId);
      setActAsUserId(effectiveId);

      if (currentSession.is_admin) {
        setFamilyUsers(await listUsers());
      } else {
        setFamilyUsers([]);
      }

      setStatus("");
    } catch {
      setSession(null);
      setActAsUserIdState(null);
      setActAsUserId(null);
    } finally {
      setAuthLoading(false);
    }
  }

  useEffect(() => {
    void bootstrapSession();
  }, []);

  useEffect(() => {
    if (actAsUserId === null || session === null) {
      return;
    }

    setActAsUserId(actAsUserId);
    void loadWorkspaceData().catch(() =>
      setStatus("Backend пока недоступен.")
    );
  }, [actAsUserId, session]);

  async function handleLogout() {
    await logout();
    setSession(null);
    setActAsUserIdState(null);
    setActAsUserId(null);
    resetComplaintChat();
  }

  function handleActAsUserChange(userId: number) {
    setActAsUserIdState(userId);
    resetComplaintChat();
  }

  useEffect(() => {
    const scrollTarget = chatMessagesRef.current;
    if (!scrollTarget) {
      return;
    }

    scrollTarget.scrollTo({
      top: scrollTarget.scrollHeight,
      behavior: "smooth"
    });
  }, [chatMessages, isAnalyzingComplaint]);

  function resetComplaintChat() {
    setChatMessages(createWelcomeMessages());
    setComplaint({
      ...emptyComplaint,
      occurred_at: new Date().toISOString().slice(0, 10)
    });
    setIsComplaintBranchesOpen(false);
    setForceComplexAnalysis(false);
    setConsultationId(null);
  }

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const savedProfile = await saveProfile(profile);
    setProfile(savedProfile);
    setStatus("Профиль сохранён.");
  }

  async function handleLabSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await createLab(lab);
    setLabs(await listLabs());
    setLab(emptyLab);
    setStatus("Показатель добавлен.");
  }

  async function handleComplaintSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const symptoms = complaint.symptoms.trim();
    if (!symptoms) {
      setStatus("Опишите симптомы в сообщении чата.");
      return;
    }

    const payload = {
      consultation_id: consultationId,
      message: symptoms,
      occurred_at: complaint.occurred_at,
      notes: complaint.notes,
      force_complex: forceComplexAnalysis
    };

    setChatMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", content: symptoms }
    ]);
    setComplaint((current) => ({ ...current, symptoms: "" }));
    setIsAnalyzingComplaint(true);
    setStatus(
      consultationId ? "Ассистент уточняет анамнез..." : "Начинаем консультацию..."
    );

    try {
      const turn = await sendConsultationChat(payload);
      setConsultationId(turn.consultation_id);
      setChatMessages((current) => [
        ...current,
        {
          id: `assistant-${turn.consultation_id}-${Date.now()}`,
          role: "assistant",
          content: turn.reply
        }
      ]);

      if (turn.phase === "conclusion" && turn.complaint) {
        setComplaints(await listComplaints());
        setComplaint({
          ...emptyComplaint,
          occurred_at: complaint.occurred_at
        });
        setConsultationId(null);
        setIsComplaintBranchesOpen(false);
        setActivePage("history");

        if (turn.ai_status === "completed") {
          setStatus(
            "Первое мнение готово. После визита к врачу добавьте его мнение в истории."
          );
        } else {
          setStatus("Консультация завершена, но ИИ-оценка не выполнена.");
        }
      } else if (turn.ai_status === "no_api_key") {
        setStatus("Добавьте AITUNNEL_API_KEY в `.env` для ответов ассистента.");
      } else if (turn.ai_status === "failed") {
        setStatus("Не удалось получить ответ. Попробуйте ещё раз.");
      } else {
        setStatus("Ответ получен. Ответьте на уточняющие вопросы ассистента.");
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Не удалось получить оценку. Попробуйте отправить сообщение ещё раз.";
      setChatMessages((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: message
        }
      ]);
      setStatus(message);
    } finally {
      setIsAnalyzingComplaint(false);
    }
  }

  async function handleCompareOpinions(complaintId: number) {
    const doctorFeedback = (doctorFeedbackDrafts[complaintId] ?? "").trim();
    if (!doctorFeedback) {
      setStatus("Введите, что сказал врач: диагноз, назначения, рекомендации.");
      return;
    }

    setComparingComplaintId(complaintId);
    setStatus("Сравниваем мнения ассистента и врача...");

    try {
      const updatedComplaint = await compareOpinions(
        complaintId,
        doctorFeedback
      );
      setComplaints(await listComplaints());
      setDoctorFeedbackDrafts((current) => ({
        ...current,
        [complaintId]: updatedComplaint.doctor_feedback
      }));
      setStatus("Сравнение мнений готово.");
    } catch {
      setStatus("Не удалось сравнить мнения. Проверьте API-ключ и попробуйте снова.");
    } finally {
      setComparingComplaintId(null);
    }
  }

  async function handleDocumentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitDocument();
  }

  async function submitDocument() {
    if (!documentFile) {
      setStatus("Выберите или перетащите файл анализа/снимка.");
      return;
    }

    setStatus("Загружаем файл и извлекаем текст...");

    try {
      const uploaded = await uploadDocument(documentFile, documentDescription);
      setDocuments(await listDocuments());
      setDocumentFile(null);
      setDocumentDescription("");
      if (documentInputRef.current) {
        documentInputRef.current.value = "";
      }

      if (uploaded.analysis_status === "completed") {
        setStatus(
          `Файл «${uploaded.filename}» загружен. Текст учтён в консультации.`
        );
      } else if (uploaded.analysis_status === "no_api_key") {
        setStatus(
          "Файл сохранён. Для OCR изображений добавьте PROXYAPI_API_KEY в `.env`."
        );
      } else {
        setStatus(
          `Файл «${uploaded.filename}» сохранён, но текст извлечён частично.`
        );
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Не удалось загрузить файл.";
      setStatus(message);
    }
  }

  function handleDocumentDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDraggingDocument(false);
    setDocumentFile(event.dataTransfer.files.item(0));
  }

  function addLifestyleSuggestion(suggestion: string) {
    if (profile.lifestyle.includes(suggestion)) {
      return;
    }

    setProfile({
      ...profile,
      lifestyle: [profile.lifestyle, suggestion].filter(Boolean).join("; ")
    });
  }

  function toggleAllergyOption(option: string) {
    const currentOptions = profile.allergies
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean);
    const nextOptions = currentOptions.includes(option)
      ? currentOptions.filter((item) => item !== option)
      : [...currentOptions.filter((item) => item !== "✅ Нет"), option];

    setProfile({
      ...profile,
      allergies: option === "✅ Нет" ? option : nextOptions.join("; ")
    });
  }

  const displayName =
    session?.effective_user.display_name ||
    session?.effective_user.username ||
    "Пользователь";

  const pageTitle = PAGE_TITLES[activePage];

  function navigateTo(page: AppPage) {
    setActivePage(page);
  }

  function startNewChat() {
    resetComplaintChat();
    navigateTo("chat");
  }

  function openComplaintHistory(complaintId: number) {
    setSelectedComplaintId(complaintId);
    navigateTo("history");
  }

  function renderChatPanel() {
    const welcomeMessage = chatMessages.find((message) => message.id === "welcome");
    const conversationMessages = chatMessages.filter(
      (message) => message.id !== "welcome"
    );

    return (
      <div className="chat-container">
        <div className="chat-header">
          <div className="avatar">🤖</div>
          <div className="info">
            <h3>ИИ медицинский консультант</h3>
            <p>● Онлайн — информационная поддержка</p>
          </div>
        </div>

        <div className="chat-messages" ref={chatMessagesRef}>
          {welcomeMessage && (
            <div className="message assistant">
              <span className="msg-avatar">🤖</span>
              <div className="bubble">{welcomeMessage.content}</div>
            </div>
          )}

          {conversationMessages.map((message) => (
            <div
              key={message.id}
              className={`message ${message.role}`}
            >
              <span className="msg-avatar">
                {message.role === "assistant" ? "🤖" : "👤"}
              </span>
              <div className="bubble">{message.content}</div>
            </div>
          ))}

          {isAnalyzingComplaint && (
            <div className="message assistant">
              <span className="msg-avatar">🤖</span>
              <div className="bubble">
                <div className="typing-indicator">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            </div>
          )}
        </div>

        <details
          className="chat-branches"
          open={isComplaintBranchesOpen}
          onToggle={(event) =>
            setIsComplaintBranchesOpen(
              (event.currentTarget as HTMLDetailsElement).open
            )
          }
        >
          <summary>Наблюдения (необязательно)</summary>
          <div className="chat-branch-list">
            <label className="chat-branch">
              <span className="chat-branch-title">Дополнительные наблюдения</span>
              <textarea
                value={complaint.notes}
                onChange={(event) =>
                  setComplaint({ ...complaint, notes: event.target.value })
                }
                placeholder="Температура, давление, пульс, что уже пробовали..."
              />
            </label>
          </div>
        </details>

        <form className="chat-input-area" onSubmit={handleComplaintSubmit}>
          <div className="chat-input-wrapper">
            <textarea
              className="chat-input"
              required
              rows={1}
              value={complaint.symptoms}
              onChange={(event) =>
                setComplaint({ ...complaint, symptoms: event.target.value })
              }
              placeholder="Напишите сообщение..."
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <button
              className="send-btn"
              type="submit"
              disabled={isAnalyzingComplaint}
              title="Отправить"
            >
              ➤
            </button>
          </div>
        </form>
      </div>
    );
  }

  function renderLabsPanel() {
    return (
      <section className="panel">
        <p className="disclaimer-note">
          Ассистент не заменяет очного врача. Загруженные файлы и показатели
          используются только для информационной поддержки.
        </p>
        <label
          className={`upload-zone ${isDraggingDocument ? "is-dragging" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setIsDraggingDocument(true);
          }}
          onDragLeave={() => setIsDraggingDocument(false)}
          onDrop={handleDocumentDrop}
          onClick={() => documentInputRef.current?.click()}
        >
          <div className="upload-icon">📤</div>
          <h3>Перетащите файлы или нажмите для выбора</h3>
          <p>JPG, PNG, PDF, TXT — анализы, рентген, заключения</p>
          <input
            ref={documentInputRef}
            type="file"
            accept=".pdf,.txt,.png,.jpg,.jpeg,.webp"
            hidden
            onChange={(event) =>
              setDocumentFile(event.target.files?.[0] ?? null)
            }
          />
        </label>
        {documentFile && (
          <p className="muted">
            Выбран: {documentFile.name}. Укажите описание и нажмите «Загрузить».
          </p>
        )}
        <p className="muted">
          Или внесите показатель вручную в таблицу ниже.
        </p>
        <form className="stack" onSubmit={handleLabSubmit}>
          <div className="row">
            <label>
              Показатель
              <input
                required
                value={lab.marker_name}
                onChange={(event) =>
                  setLab({ ...lab, marker_name: event.target.value })
                }
                placeholder="Например: гемоглобин, глюкоза, ферритин"
              />
            </label>
            <label>
              Значение
              <input
                required
                type="number"
                step="any"
                value={lab.value}
                onChange={(event) =>
                  setLab({ ...lab, value: Number(event.target.value) })
                }
              />
            </label>
          </div>
          <div className="row">
            <label>
              Единицы
              <input
                value={lab.unit}
                onChange={(event) =>
                  setLab({ ...lab, unit: event.target.value })
                }
                placeholder="г/л, ммоль/л, Ед/мл"
              />
            </label>
            <label>
              Дата
              <input
                type="date"
                value={lab.measured_at}
                onChange={(event) =>
                  setLab({ ...lab, measured_at: event.target.value })
                }
              />
            </label>
          </div>
          <label>
            Норма по бланку
            <textarea
              value={lab.reference_range}
              onChange={(event) =>
                setLab({ ...lab, reference_range: event.target.value })
              }
              placeholder="120–160 или 3.9–6.1"
            />
          </label>
          <label>
            Комментарий
            <textarea
              value={lab.comment}
              onChange={(event) =>
                setLab({ ...lab, comment: event.target.value })
              }
            />
          </label>
          <button type="submit">Добавить показатель</button>
        </form>

        <form className="stack panel-divider" onSubmit={handleDocumentSubmit}>
          <h3 className="panel-subtitle lab-form-section">Описание и загрузка</h3>
          <label>
            Описание файла
            <textarea
              value={documentDescription}
              onChange={(event) =>
                setDocumentDescription(event.target.value)
              }
              placeholder="ОАК от 20.05, рентген грудной клетки, УЗИ..."
            />
          </label>
          <button type="submit">Загрузить файл</button>
          {documents.length > 0 && (
            <div className="lab-list">
              {documents.slice(0, 8).map((item) => (
                <article key={item.id} className="lab-item">
                  <strong>{item.filename}</strong>
                  <span>{item.description || "Без описания"}</span>
                  <small>
                    {item.analysis_status === "completed"
                      ? "Текст извлечён и доступен ассистенту"
                      : `Статус: ${item.analysis_status}`}
                  </small>
                </article>
              ))}
            </div>
          )}
        </form>
      </section>
    );
  }

  function renderTrendsPanel() {
    return (
      <section className="panel">
        <p className="muted">
          Динамика показателей относительно предыдущих значений.
        </p>
        <div className="lab-list">
          {labs.length === 0 && (
            <p className="muted">Пока нет внесённых показателей.</p>
          )}
          {labs.map((item) => {
            const delta =
              item.trend?.delta !== null && item.trend?.delta !== undefined
                ? `${item.trend.delta > 0 ? "+" : ""}${item.trend.delta}`
                : "";

            return (
              <article key={item.id} className="lab-item">
                <strong>{item.marker_name}</strong>
                <span>
                  {item.value} {item.unit} от {item.measured_at}
                </span>
                <small>
                  {item.trend?.direction === "baseline"
                    ? "Базовое значение"
                    : `Динамика: ${item.trend?.direction ?? "нет данных"} ${delta}`}
                </small>
              </article>
            );
          })}
        </div>
      </section>
    );
  }

  function renderHistoryPanel() {
    const visibleComplaints =
      selectedComplaintId !== null
        ? complaints.filter((item) => item.id === selectedComplaintId)
        : complaints;

    return (
      <section className="panel">
        <p className="muted">
          Шаг 2: мнение врача после визита → Шаг 3: сравнение с первым мнением
          ассистента.
        </p>
        {selectedComplaintId !== null && (
          <button
            className="secondary-button"
            type="button"
            onClick={() => setSelectedComplaintId(null)}
          >
            ← Все обращения
          </button>
        )}
        <div className="lab-list history-list">
          {visibleComplaints.length === 0 && (
            <p className="muted">Пока нет сохранённых обращений.</p>
          )}
          {visibleComplaints.map((item) => (
            <article key={item.id} className="complaint-item chat-thread">
              <div className="complaint-header">
                <strong>{item.occurred_at}</strong>
                {item.ai_status === "completed" && item.ai_urgency && (
                  <span className={`urgency urgency-${item.ai_urgency}`}>
                    {item.ai_urgency === "urgent"
                      ? "Срочно"
                      : item.ai_urgency === "soon"
                        ? "Обратиться скоро"
                        : "Планово"}
                  </span>
                )}
              </div>

              <div className="chat-message chat-message-user">
                <span className="chat-message-label">Шаг 1 — симптомы</span>
                <p>{item.symptoms}</p>
              </div>

              {item.notes && (
                <div className="chat-branch-comment">
                  <span className="chat-branch-title">Наблюдения</span>
                  <p>{item.notes}</p>
                </div>
              )}

              <div className="chat-message chat-message-assistant">
                <span className="chat-message-label">
                  Первое мнение ассистента
                </span>
                <p>{formatAssistantReply(item)}</p>
              </div>

              <div className="chat-branch-comment chat-branch-comment-form">
                <span className="chat-branch-title">Мнение врача</span>
                <textarea
                  value={doctorFeedbackDrafts[item.id] ?? ""}
                  onChange={(event) =>
                    setDoctorFeedbackDrafts((current) => ({
                      ...current,
                      [item.id]: event.target.value
                    }))
                  }
                  placeholder="Диагноз, назначения, рекомендации..."
                  rows={3}
                />
                <button
                  className="comparison-button"
                  type="button"
                  disabled={comparingComplaintId === item.id}
                  onClick={() => handleCompareOpinions(item.id)}
                >
                  {comparingComplaintId === item.id
                    ? "Анализируем..."
                    : "Сравнить мнения"}
                </button>
              </div>

              {item.ai_opinion_comparison && (
                <div className="chat-message chat-message-assistant chat-message-comparison">
                  <span className="chat-message-label">Сравнение мнений</span>
                  <OpinionComparisonView raw={item.ai_opinion_comparison} />
                </div>
              )}
            </article>
          ))}
        </div>
      </section>
    );
  }

  function renderDashboard() {
    const profileFilled = [
      profile.full_name,
      profile.age,
      profile.birth_date,
      profile.sex,
      profile.blood_type,
      profile.diabetes_status,
      profile.cardiovascular_status,
      profile.chronic_conditions,
      profile.allergies,
      profile.activity_level,
      profile.smoking_status,
      profile.sleep_hours,
      profile.stress_level,
      profile.family_members
    ].filter(Boolean).length;

    return (
      <div className="page-dashboard">
        <div className="welcome-banner">
          <div className="welcome-banner-content">
            <h2>Добро пожаловать, {displayName}!</h2>
            <p>
              Ваш ИИ-консультант готов помочь. Выберите раздел или начните диалог.
            </p>
          </div>
          <button
            className="dashboard-logout-button"
            type="button"
            onClick={() => void handleLogout()}
          >
            Выйти
          </button>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon blue">💬</div>
            <div className="stat-value">{complaints.length}</div>
            <div className="stat-label">Обращений</div>
          </div>
          <div className="stat-card">
            <div className="stat-icon green">📋</div>
            <div className="stat-value">{profileFilled}</div>
            <div className="stat-label">Полей анкеты</div>
          </div>
          <div className="stat-card">
            <div className="stat-icon orange">🔬</div>
            <div className="stat-value">{labs.length + documents.length}</div>
            <div className="stat-label">Анализов и файлов</div>
          </div>
          <div className="stat-card">
            <div className="stat-icon purple">👨‍👩‍👧‍👦</div>
            <div className="stat-value">
              {session?.is_admin ? familyUsers.length : 1}
            </div>
            <div className="stat-label">
              {session?.is_admin ? "Пользователей" : "Профиль"}
            </div>
          </div>
        </div>

        <h3 className="section-heading">Быстрые действия</h3>
        <div className="quick-actions">
          <button
            className="quick-action-card"
            type="button"
            onClick={() => navigateTo("chat")}
          >
            <div className="action-icon">💬</div>
            <div className="action-title">Консультация</div>
            <div className="action-desc">Спросить ИИ-ассистента</div>
          </button>
          <button
            className="quick-action-card"
            type="button"
            onClick={() => navigateTo("questionnaire")}
          >
            <div className="action-icon">📋</div>
            <div className="action-title">Анкета</div>
            <div className="action-desc">Медицинский профиль</div>
          </button>
          <button
            className="quick-action-card"
            type="button"
            onClick={() => navigateTo("labs")}
          >
            <div className="action-icon">📷</div>
            <div className="action-title">Анализы</div>
            <div className="action-desc">Файлы и показатели</div>
          </button>
          <button
            className="quick-action-card"
            type="button"
            onClick={() => navigateTo("history")}
          >
            <div className="action-icon">📚</div>
            <div className="action-title">История</div>
            <div className="action-desc">Сравнение мнений</div>
          </button>
          <button
            className="quick-action-card"
            type="button"
            onClick={() => navigateTo("fitness")}
          >
            <div className="action-icon">💪</div>
            <div className="action-title">Фитнес</div>
            <div className="action-desc">Скоро</div>
          </button>
          <button
            className="quick-action-card"
            type="button"
            onClick={() => navigateTo("nutrition")}
          >
            <div className="action-icon">🥗</div>
            <div className="action-title">Питание</div>
            <div className="action-desc">AI-меню на неделю</div>
          </button>
        </div>
      </div>
    );
  }

  function renderQuestionnaire() {
    return (
      <div className="questionnaire-card">
        <div className="questionnaire-header">
          <h2>📋 Анкета здоровья</h2>
          <p>
            Медицинский профиль используется ассистентом при консультациях и
            анализе показателей.
          </p>
        </div>
        <form className="questionnaire-body stack" onSubmit={handleProfileSubmit}>
          <div className="question-section">
            <h3><span className="section-icon">👤</span> Основная информация</h3>
            <div className="question-grid">
              <div className="question-item">
                <label>
                  ФИО
                  <input
                    value={profile.full_name}
                    onChange={(event) =>
                      setProfile({ ...profile, full_name: event.target.value })
                    }
                    placeholder="Иванов Иван Иванович"
                  />
                </label>
              </div>
              <div className="question-item">
                <label>
                  Дата рождения
                  <input
                    type="date"
                    value={profile.birth_date ?? ""}
                    onChange={(event) =>
                      setProfile({
                        ...profile,
                        birth_date: event.target.value || null
                      })
                    }
                  />
                </label>
              </div>
              <div className="question-item">
                <label>
                  Возраст
                  <input
                    type="number"
                    min={0}
                    max={130}
                    value={profile.age ?? ""}
                    onChange={(event) =>
                      setProfile({
                        ...profile,
                        age: event.target.value
                          ? Number(event.target.value)
                          : null
                      })
                    }
                  />
                </label>
              </div>
              <div className="question-item">
                <span className="question-label">Пол</span>
                <div className="radio-group">
                  {["Мужской", "Женский"].map((value) => (
                    <label className="radio-option" key={value}>
                      <input
                        type="radio"
                        name="sex"
                        checked={profile.sex === value}
                        onChange={() => setProfile({ ...profile, sex: value })}
                      />
                      <span>{value}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="question-item">
                <label>
                  Группа крови
                  <select
                    value={profile.blood_type}
                    onChange={(event) =>
                      setProfile({ ...profile, blood_type: event.target.value })
                    }
                  >
                    <option value="">Не знаю</option>
                    {bloodTypeOptions.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="question-item">
                <label>
                  Рост, см
                  <input
                    type="number"
                    value={profile.height_cm ?? ""}
                    onChange={(event) =>
                      setProfile({
                        ...profile,
                        height_cm: event.target.value
                          ? Number(event.target.value)
                          : null
                      })
                    }
                  />
                </label>
              </div>
              <div className="question-item">
                <label>
                  Вес, кг
                  <input
                    type="number"
                    value={profile.weight_kg ?? ""}
                    onChange={(event) =>
                      setProfile({
                        ...profile,
                        weight_kg: event.target.value
                          ? Number(event.target.value)
                          : null
                      })
                    }
                  />
                </label>
              </div>
            </div>
          </div>

          <div className="question-section">
            <h3><span className="section-icon">🏥</span> Хронические заболевания</h3>
            <div className="question-grid">
              <div className="question-item">
                <span className="question-label">Диагноз «сахарный диабет»?</span>
                <div className="radio-group">
                  {["Нет", "Тип 1", "Тип 2", "Преддиабет"].map((value) => (
                    <label className="radio-option" key={value}>
                      <input
                        type="radio"
                        name="diabetes"
                        checked={profile.diabetes_status === value}
                        onChange={() =>
                          setProfile({ ...profile, diabetes_status: value })
                        }
                      />
                      <span>{value}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="question-item">
                <span className="question-label">Заболевания ССС?</span>
                <div className="radio-group">
                  {["Нет", "Гипертония", "Аритмия", "Другое"].map((value) => (
                    <label className="radio-option" key={value}>
                      <input
                        type="radio"
                        name="cardio"
                        checked={profile.cardiovascular_status === value}
                        onChange={() =>
                          setProfile({
                            ...profile,
                            cardiovascular_status: value
                          })
                        }
                      />
                      <span>{value}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="question-item question-item-wide">
                <label>
                  Другие хронические заболевания
                  <textarea
                    value={profile.chronic_conditions}
                    onChange={(event) =>
                      setProfile({
                        ...profile,
                        chronic_conditions: event.target.value
                      })
                    }
                    placeholder="Астма, болезни ЖКТ, щитовидная железа, операции..."
                  />
                </label>
              </div>
            </div>
          </div>

          <div className="question-section">
            <h3><span className="section-icon">⚠️</span> Аллергии</h3>
            <div className="question-item">
              <span className="question-label">Выберите известные аллергии</span>
              <div className="tag-select">
                {allergyOptions.map((option) => (
                  <button
                    className={`tag-option ${
                      profile.allergies.split(";").map((item) => item.trim()).includes(option)
                        ? "selected"
                        : ""
                    }`}
                    key={option}
                    type="button"
                    onClick={() => toggleAllergyOption(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
              <textarea
                value={profile.allergies}
                onChange={(event) =>
                  setProfile({ ...profile, allergies: event.target.value })
                }
                placeholder="Можно дописать реакцию: сыпь, отёк, анафилаксия..."
              />
            </div>
          </div>

          <div className="question-section">
            <h3><span className="section-icon">💊</span> Постоянные лекарства</h3>
            <div className="question-item">
              <label>
                Препараты, которые принимаете регулярно
                <textarea
                  value={profile.medications}
                  onChange={(event) =>
                    setProfile({ ...profile, medications: event.target.value })
                  }
                  placeholder="Например: Эналаприл 5 мг утром, витамин D3 2000 МЕ..."
                />
              </label>
            </div>
          </div>

          <div className="question-section">
            <h3><span className="section-icon">🏃</span> Образ жизни</h3>
            <div className="question-grid">
              <div className="question-item">
                <span className="question-label">Физическая активность</span>
                <div className="radio-group">
                  {["Сидячий", "Умеренный", "Активный", "Спортсмен"].map((value) => (
                    <label className="radio-option" key={value}>
                      <input
                        type="radio"
                        name="activity"
                        checked={profile.activity_level === value}
                        onChange={() =>
                          setProfile({ ...profile, activity_level: value })
                        }
                      />
                      <span>{value}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="question-item">
                <span className="question-label">Курение</span>
                <div className="radio-group">
                  {["Не курю", "Бросил", "Курю"].map((value) => (
                    <label className="radio-option" key={value}>
                      <input
                        type="radio"
                        name="smoking"
                        checked={profile.smoking_status === value}
                        onChange={() =>
                          setProfile({ ...profile, smoking_status: value })
                        }
                      />
                      <span>{value}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="question-item">
                <label>
                  Сон, часов в сутки
                  <input
                    type="number"
                    min={0}
                    max={24}
                    value={profile.sleep_hours ?? ""}
                    onChange={(event) =>
                      setProfile({
                        ...profile,
                        sleep_hours: event.target.value
                          ? Number(event.target.value)
                          : null
                      })
                    }
                    placeholder="7–8"
                  />
                </label>
              </div>
              <div className="question-item">
                <span className="question-label">Уровень стресса</span>
                <div className="radio-group">
                  {["😊 Низкий", "😐 Средний", "😰 Высокий"].map((value) => (
                    <label className="radio-option" key={value}>
                      <input
                        type="radio"
                        name="stress"
                        checked={profile.stress_level === value}
                        onChange={() =>
                          setProfile({ ...profile, stress_level: value })
                        }
                      />
                      <span>{value}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="question-item question-item-wide">
                <label>
                  Дополнительно об образе жизни
                  <textarea
                    value={profile.lifestyle}
                    onChange={(event) =>
                      setProfile({ ...profile, lifestyle: event.target.value })
                    }
                  />
                </label>
                <div className="chips" aria-label="Варианты образа жизни">
                  {lifestyleSuggestions.map((suggestion) => (
                    <button
                      className="chip"
                      key={suggestion}
                      type="button"
                      onClick={() => addLifestyleSuggestion(suggestion)}
                    >
                      + {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="question-section">
            <h3><span className="section-icon">👨‍👩‍👧</span> Семья</h3>
            <div className="question-grid">
              <div className="question-item">
                <label>
                  Наследственные заболевания
                  <textarea
                    value={profile.family_history}
                    onChange={(event) =>
                      setProfile({
                        ...profile,
                        family_history: event.target.value
                      })
                    }
                    placeholder="Диабет, инфаркты, инсульты, онкология у родственников..."
                  />
                </label>
              </div>
              <div className="question-item">
                <label>
                  Членов семьи
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={profile.family_members ?? ""}
                    onChange={(event) =>
                      setProfile({
                        ...profile,
                        family_members: event.target.value
                          ? Number(event.target.value)
                          : null
                      })
                    }
                    placeholder="4"
                  />
                </label>
              </div>
              <div className="question-item question-item-wide">
                <label>
                  Примечания
                  <textarea
                    value={profile.notes}
                    onChange={(event) =>
                      setProfile({ ...profile, notes: event.target.value })
                    }
                    placeholder="Что ещё важно знать ассистенту..."
                  />
                </label>
              </div>
            </div>
          </div>
          <button type="submit">Сохранить анкету ✓</button>
        </form>
      </div>
    );
  }

  function renderComingSoon(page: "nutrition" | "fitness") {
    const isFitness = page === "fitness";
    return (
      <section className="panel">
        <div className={isFitness ? "fitness-hero" : "nutrition-hero"}>
          <h2>{isFitness ? "💪 ИИ Фитнес-тренер" : "🥗 ИИ Нутрициолог"}</h2>
          <p>
            {isFitness
              ? "Персональные тренировки с учётом профиля здоровья — в разработке."
              : "Планы питания и подсчёт КБЖУ — в разработке."}
          </p>
        </div>
        <div className="empty-state">
          <p className="muted">
            Раздел появится в следующих версиях. Пока используйте консультацию,
            анкету и анализы.
          </p>
          <button
            className="secondary-button"
            type="button"
            onClick={() => navigateTo("dashboard")}
          >
            ← На главную
          </button>
        </div>
      </section>
    );
  }

  function renderMainContent() {
    switch (activePage) {
      case "dashboard":
        return renderDashboard();
      case "chat":
        return renderChatPanel();
      case "questionnaire":
        return renderQuestionnaire();
      case "labs":
        return renderLabsPanel();
      case "trends":
        return renderTrendsPanel();
      case "history":
        return renderHistoryPanel();
      case "nutrition":
        return <NutritionPlanner profile={profile} complaints={complaints} />;
      case "fitness":
        return renderComingSoon("fitness");
      default:
        return renderDashboard();
    }
  }

  if (authLoading) {
    return (
      <div className="login-screen">
        <div className="login-card">
          <div className="login-logo">
            <div className="icon">🩺</div>
            <h1>Медицинский консультант</h1>
          </div>
          <p className="muted">Загрузка...</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return <LoginPage onSuccess={() => void bootstrapSession()} />;
  }

  const userRole = session.is_admin ? "Администратор" : "Семья";

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Навигация">
        <div className="sidebar-header">
          <h2>
            <span className="app-icon">🩺</span>
            МедКонсультант
          </h2>
          <p>v1.0 · локально</p>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section">
            <div className="nav-section-title">Главное</div>
            <button
              className={`nav-item ${activePage === "dashboard" ? "is-active" : ""}`}
              type="button"
              onClick={() => navigateTo("dashboard")}
            >
              <span className="icon">🏠</span>
              Главная
            </button>
            <button
              className={`nav-item ${activePage === "chat" ? "is-active" : ""}`}
              type="button"
              onClick={() => navigateTo("chat")}
            >
              <span className="icon">💬</span>
              Чат с ИИ
              {complaints.length > 0 && (
                <span className="badge">{complaints.length}</span>
              )}
            </button>
            <button
              className={`nav-item ${activePage === "questionnaire" ? "is-active" : ""}`}
              type="button"
              onClick={() => navigateTo("questionnaire")}
            >
              <span className="icon">📋</span>
              Анкета здоровья
            </button>
          </div>

          <div className="nav-section">
            <div className="nav-section-title">Данные</div>
            <button
              className={`nav-item ${activePage === "labs" ? "is-active" : ""}`}
              type="button"
              onClick={() => navigateTo("labs")}
            >
              <span className="icon">🔬</span>
              Анализы и снимки
            </button>
            <button
              className={`nav-item ${activePage === "trends" ? "is-active" : ""}`}
              type="button"
              onClick={() => navigateTo("trends")}
            >
              <span className="icon">📈</span>
              Тренды
            </button>
            <button
              className={`nav-item ${activePage === "history" ? "is-active" : ""}`}
              type="button"
              onClick={() => {
                setSelectedComplaintId(null);
                navigateTo("history");
              }}
            >
              <span className="icon">📚</span>
              История
            </button>
          </div>

          <div className="nav-section">
            <div className="nav-section-title">Специалисты</div>
            <button
              className={`nav-item ${activePage === "fitness" ? "is-active" : ""}`}
              type="button"
              onClick={() => navigateTo("fitness")}
            >
              <span className="icon">💪</span>
              ИИ Фитнес-тренер
            </button>
            <button
              className={`nav-item ${activePage === "nutrition" ? "is-active" : ""}`}
              type="button"
              onClick={() => navigateTo("nutrition")}
            >
              <span className="icon">🥗</span>
              ИИ Нутрициолог
            </button>
          </div>
        </nav>

        <div className="sidebar-chat-section">
          <div className="section-header">
            <span className="section-title">История диалогов</span>
            <div className="sidebar-chat-section-actions">
              <button
                className={`sidebar-collapse-btn ${isChatHistoryCollapsed ? "is-collapsed" : ""}`}
                type="button"
                title="Свернуть список"
                onClick={() =>
                  setIsChatHistoryCollapsed(!isChatHistoryCollapsed)
                }
              >
                ▾
              </button>
            </div>
          </div>
          {!isChatHistoryCollapsed && (
            <div className="sidebar-chat-list">
              {complaints.length === 0 && (
                <p className="sidebar-chat-time" style={{ padding: "8px 10px" }}>
                  Нет сохранённых обращений
                </p>
              )}
              {complaints.slice(0, 12).map((item) => (
                <button
                  key={item.id}
                  className={`sidebar-chat-item ${selectedComplaintId === item.id && activePage === "history" ? "is-active" : ""}`}
                  type="button"
                  onClick={() => openComplaintHistory(item.id)}
                >
                  <div className="sidebar-chat-title">
                    {formatComplaintTitle(item.symptoms, item.occurred_at)}
                  </div>
                  <div className="sidebar-chat-time">{item.occurred_at}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="sidebar-footer">
          <div className="user-info">
            <div className="user-avatar">{getUserInitials(displayName)}</div>
            <div className="user-details">
              <div className="name">{displayName}</div>
              <div className="role">{userRole}</div>
            </div>
            <button
              className="logout-btn"
              type="button"
              title="Выйти"
              onClick={() => void handleLogout()}
            >
              🚪
            </button>
          </div>
          {session.is_admin && familyUsers.length > 0 && (
            <label className="sidebar-user-select">
              <select
                value={actAsUserId ?? session.effective_user.id}
                onChange={(event) =>
                  handleActAsUserChange(Number(event.target.value))
                }
              >
                {familyUsers.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.display_name || user.username}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          {activePage === "chat" && (
            <button
              className="secondary-button"
              type="button"
              onClick={startNewChat}
            >
              + Новый диалог
            </button>
          )}
          <h2>{pageTitle}</h2>
          <div className="topbar-actions">
            {activePage === "chat" && (
              <>
                <label className="toolbar-field">
                  <span>Дата</span>
                  <input
                    type="date"
                    value={complaint.occurred_at}
                    onChange={(event) =>
                      setComplaint({
                        ...complaint,
                        occurred_at: event.target.value
                      })
                    }
                  />
                </label>
                <label className="toolbar-toggle">
                  <input
                    type="checkbox"
                    checked={forceComplexAnalysis}
                    onChange={(event) =>
                      setForceComplexAnalysis(event.target.checked)
                    }
                  />
                  <span>Сложный случай</span>
                </label>
              </>
            )}
          </div>
        </header>

        {status && <div className="status-banner">{status}</div>}

        <div
          className={
            activePage === "chat" ? "content-area content-area-chat" : "content-area"
          }
        >
          {renderMainContent()}
        </div>
      </main>
    </div>
  );
}

export default App;
