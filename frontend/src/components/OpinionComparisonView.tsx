type OpinionComparisonData = {
  reply: string;
  agreements: string;
  disagreements: string;
  recommendations: string;
  questions_for_doctor: string[];
};

function parseOpinionComparison(raw: string): OpinionComparisonData | null {
  if (!raw.trim()) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<OpinionComparisonData>;
    if (typeof parsed !== "object" || parsed === null) {
      return null;
    }

    return {
      reply: parsed.reply?.trim() ?? "",
      agreements: parsed.agreements?.trim() ?? "",
      disagreements: parsed.disagreements?.trim() ?? "",
      recommendations: parsed.recommendations?.trim() ?? "",
      questions_for_doctor: Array.isArray(parsed.questions_for_doctor)
        ? parsed.questions_for_doctor
            .map((item) => String(item).trim())
            .filter(Boolean)
        : []
    };
  } catch {
    return null;
  }
}

export function OpinionComparisonView({ raw }: { raw: string }) {
  const comparison = parseOpinionComparison(raw);

  if (!comparison) {
    return <p>{raw}</p>;
  }

  return (
    <div className="comparison-sections">
      {comparison.reply && (
        <section className="comparison-section">
          <h4>Итог</h4>
          <p>{comparison.reply}</p>
        </section>
      )}
      {comparison.agreements && (
        <section className="comparison-section comparison-agreements">
          <h4>Совпало</h4>
          <p>{comparison.agreements}</p>
        </section>
      )}
      {comparison.disagreements && (
        <section className="comparison-section comparison-disagreements">
          <h4>Расходится</h4>
          <p>{comparison.disagreements}</p>
        </section>
      )}
      {comparison.recommendations && (
        <section className="comparison-section comparison-recommendations">
          <h4>Что делать дальше</h4>
          <p>{comparison.recommendations}</p>
        </section>
      )}
      {comparison.questions_for_doctor.length > 0 && (
        <section className="comparison-section comparison-questions">
          <h4>Вопросы врачу</h4>
          <ul>
            {comparison.questions_for_doctor.map((question, index) => (
              <li key={`${index}-${question}`}>{question}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function formatAssistantReply(item: {
  ai_status: string;
  ai_diagnosis: string;
  ai_treatment: string;
  ai_doctor_questions: string;
  ai_analysis: string;
}): string {
  if (item.ai_status === "completed") {
    const parts: string[] = [];
    if (item.ai_diagnosis) {
      parts.push(`Диагноз:\n${item.ai_diagnosis}`);
    }
    if (item.ai_treatment) {
      parts.push(`План лечения:\n${item.ai_treatment}`);
    }
    if (item.ai_doctor_questions) {
      parts.push(`Что спросить у врача:\n${item.ai_doctor_questions}`);
    }
    return parts.join("\n\n");
  }

  if (item.ai_status === "no_api_key") {
    return "Жалоба сохранена. Для ИИ-оценки нужен AITUNNEL_API_KEY в `.env`.";
  }

  if (item.ai_analysis) {
    return item.ai_analysis;
  }

  return "Жалоба сохранена, но ИИ-оценка не выполнена.";
}
