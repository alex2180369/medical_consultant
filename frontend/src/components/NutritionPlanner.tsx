import { useMemo, useState } from "react";

import {
  ComplaintRecord,
  MedicalProfile,
  generateNutritionMenu
} from "../api";

type MealType = "breakfast" | "lunch" | "dinner";
type NutritionView = "home" | "day" | "shopping" | "pantry" | "week";

type Meal = {
  type: MealType;
  label: string;
  title: string;
  description: string;
  prepTime: string;
  difficulty: "легко" | "средне";
  tags: string[];
  cookMethod: string;
  ingredients: string[];
  steps: string[];
  macros: {
    calories: number;
    protein: number;
    fat: number;
    carbs: number;
  };
};

type DayMenu = {
  id: string;
  title: string;
  subtitle: string;
  meals: Meal[];
};

type ShoppingCategory = {
  title: string;
  icon: string;
  items: string[];
};

type NutritionPlannerProps = {
  profile: MedicalProfile;
  complaints: ComplaintRecord[];
};

const mealLabels: Record<MealType, string> = {
  breakfast: "Завтрак",
  lunch: "Обед",
  dinner: "Ужин"
};

const dayShortLabels: Record<string, { icon: string; label: string }> = {
  monday: { icon: "🌅", label: "Пн" },
  tuesday: { icon: "☀️", label: "Вт" },
  wednesday: { icon: "🌿", label: "Ср" },
  thursday: { icon: "🍂", label: "Чт" },
  friday: { icon: "🎉", label: "Пт" },
  saturday: { icon: "🌸", label: "Сб" },
  sunday: { icon: "🙂", label: "Вс" }
};

const pantryItems = [
  "гречка",
  "рис",
  "макароны",
  "яйца",
  "овсянка",
  "картофель",
  "лук",
  "морковь",
  "чеснок",
  "растительное масло",
  "специи",
  "чай",
  "кофе",
  "мука",
  "сахар"
];

const weekMenu: DayMenu[] = [
  {
    id: "monday",
    title: "Понедельник",
    subtitle: "Мягкий старт недели: белок, крупы и овощи.",
    meals: [
      {
        type: "breakfast",
        label: "Завтрак",
        title: "Омлет с помидором и зеленью",
        description: "Быстрый белковый завтрак из продуктов, которые легко найти.",
        prepTime: "15 минут",
        difficulty: "легко",
        tags: ["быстро", "полезно"],
        cookMethod: "Готовить на сковороде под крышкой 7-8 минут на слабом огне.",
        ingredients: ["2 яйца", "помидор", "зелень", "молоко 2 ст. л.", "специи"],
        steps: [
          "Взбейте яйца с молоком и щепоткой специй.",
          "Нарежьте помидор, слегка прогрейте на сковороде.",
          "Влейте яйца, добавьте зелень и готовьте под крышкой."
        ],
        macros: { calories: 310, protein: 20, fat: 20, carbs: 10 }
      },
      {
        type: "lunch",
        label: "Обед",
        title: "Гречка с курицей и салатом",
        description: "Сытный обед, который удобно приготовить сразу на два дня.",
        prepTime: "35 минут",
        difficulty: "легко",
        tags: ["сытно", "можно приготовить заранее"],
        cookMethod: "Курицу тушить 20 минут, гречку отварить отдельно.",
        ingredients: ["куриное филе", "гречка", "огурец", "капуста", "зелень"],
        steps: [
          "Отварите гречку до мягкости.",
          "Курицу нарежьте и потушите с луком, морковью и специями.",
          "Сделайте простой салат из овощей и зелени."
        ],
        macros: { calories: 620, protein: 42, fat: 18, carbs: 70 }
      },
      {
        type: "dinner",
        label: "Ужин",
        title: "Минтай с картофелем и морковью",
        description: "Лёгкий ужин с рыбой без дорогих морепродуктов.",
        prepTime: "40 минут",
        difficulty: "легко",
        tags: ["полезно", "сытно"],
        cookMethod: "Запекать в духовке 25 минут при 180 градусах.",
        ingredients: ["минтай", "картофель", "морковь", "лук", "лимон"],
        steps: [
          "Выложите рыбу и овощи в форму.",
          "Добавьте специи, немного масла и ломтик лимона.",
          "Запекайте до мягкости картофеля."
        ],
        macros: { calories: 480, protein: 34, fat: 12, carbs: 58 }
      }
    ]
  },
  {
    id: "tuesday",
    title: "Вторник",
    subtitle: "Больше клетчатки и тёплый домашний суп.",
    meals: [
      {
        type: "breakfast",
        label: "Завтрак",
        title: "Овсянка с яблоком и йогуртом",
        description: "Мягкий завтрак для спокойного начала дня.",
        prepTime: "12 минут",
        difficulty: "легко",
        tags: ["быстро", "полезно"],
        cookMethod: "Варить овсянку 5-7 минут, яблоко добавить в конце.",
        ingredients: ["овсянка", "яблоко", "натуральный йогурт", "корица"],
        steps: [
          "Сварите овсянку на воде или молоке.",
          "Добавьте нарезанное яблоко и корицу.",
          "Подавайте с ложкой йогурта."
        ],
        macros: { calories: 360, protein: 14, fat: 8, carbs: 58 }
      },
      {
        type: "lunch",
        label: "Обед",
        title: "Суп с говядиной и овощами",
        description: "Домашний суп на два дня без сложных ингредиентов.",
        prepTime: "70 минут",
        difficulty: "средне",
        tags: ["сытно", "можно приготовить заранее"],
        cookMethod: "Варить на слабом огне 60 минут, овощи добавить за 20 минут.",
        ingredients: ["говядина", "картофель", "капуста", "лук", "морковь"],
        steps: [
          "Отварите говядину до мягкости.",
          "Добавьте картофель, капусту, лук и морковь.",
          "Доведите до вкуса специями и зеленью."
        ],
        macros: { calories: 520, protein: 34, fat: 20, carbs: 48 }
      },
      {
        type: "dinner",
        label: "Ужин",
        title: "Паста с овощами и творожным соусом",
        description: "Ужин без тяжёлого соуса, но с приятной сливочностью.",
        prepTime: "25 минут",
        difficulty: "легко",
        tags: ["быстро", "полезно"],
        cookMethod: "Пасту отварить, овощи тушить 10 минут на сковороде.",
        ingredients: ["паста", "кабачок", "перец", "творог", "зелень"],
        steps: [
          "Отварите пасту до готовности.",
          "Овощи нарежьте и потушите.",
          "Смешайте творог с зеленью и добавьте к пасте."
        ],
        macros: { calories: 540, protein: 24, fat: 16, carbs: 74 }
      }
    ]
  },
  {
    id: "wednesday",
    title: "Среда",
    subtitle: "Творог, рис и запеканка для середины недели.",
    meals: [
      {
        type: "breakfast",
        label: "Завтрак",
        title: "Сырники с йогуртом",
        description: "Любимый домашний завтрак, который можно сделать менее сладким.",
        prepTime: "25 минут",
        difficulty: "средне",
        tags: ["сытно", "можно приготовить заранее"],
        cookMethod: "Обжарить на слабом огне по 3-4 минуты с каждой стороны.",
        ingredients: ["творог", "яйцо", "мука", "йогурт", "ягоды"],
        steps: [
          "Смешайте творог, яйцо и немного муки.",
          "Сформируйте сырники.",
          "Обжарьте и подайте с йогуртом."
        ],
        macros: { calories: 430, protein: 28, fat: 14, carbs: 48 }
      },
      {
        type: "lunch",
        label: "Обед",
        title: "Рис с индейкой и овощами",
        description: "Нежное мясо и гарнир без повторения вчерашней пасты.",
        prepTime: "35 минут",
        difficulty: "легко",
        tags: ["сытно", "полезно"],
        cookMethod: "Индейку тушить 18-20 минут, рис отварить отдельно.",
        ingredients: ["индейка", "рис", "перец", "зелёный горошек", "зелень"],
        steps: [
          "Отварите рис.",
          "Индейку нарежьте и потушите с овощами.",
          "Соедините с рисом и зеленью."
        ],
        macros: { calories: 610, protein: 40, fat: 14, carbs: 78 }
      },
      {
        type: "dinner",
        label: "Ужин",
        title: "Овощная запеканка с сыром",
        description: "Тёплый ужин, который можно разогреть на следующий день.",
        prepTime: "45 минут",
        difficulty: "легко",
        tags: ["полезно", "можно приготовить заранее"],
        cookMethod: "Запекать 30 минут при 180 градусах.",
        ingredients: ["кабачок", "капуста", "помидор", "сыр", "яйцо"],
        steps: [
          "Нарежьте овощи и выложите в форму.",
          "Смешайте яйцо с небольшим количеством молока.",
          "Залейте овощи, посыпьте сыром и запеките."
        ],
        macros: { calories: 420, protein: 22, fat: 22, carbs: 34 }
      }
    ]
  },
  {
    id: "thursday",
    title: "Четверг",
    subtitle: "Простые блюда с рыбой, супом и овощами.",
    meals: [
      {
        type: "breakfast",
        label: "Завтрак",
        title: "Бутерброды с творожным сыром и яйцом",
        description: "Быстро, понятно и удобно перед работой.",
        prepTime: "10 минут",
        difficulty: "легко",
        tags: ["быстро"],
        cookMethod: "Яйцо отварить 8-9 минут, хлеб слегка подсушить.",
        ingredients: ["цельнозерновой хлеб", "творожный сыр", "яйцо", "огурец"],
        steps: [
          "Подсушите хлеб.",
          "Смажьте творожным сыром.",
          "Добавьте яйцо и огурец."
        ],
        macros: { calories: 390, protein: 22, fat: 18, carbs: 38 }
      },
      {
        type: "lunch",
        label: "Обед",
        title: "Картофельный суп с курицей",
        description: "Простой суп из доступных продуктов.",
        prepTime: "50 минут",
        difficulty: "легко",
        tags: ["сытно", "можно приготовить заранее"],
        cookMethod: "Варить 40-45 минут, зелень добавить перед подачей.",
        ingredients: ["курица", "картофель", "лук", "морковь", "зелень"],
        steps: [
          "Сварите курицу и достаньте мясо.",
          "Добавьте картофель, лук и морковь.",
          "Верните мясо в суп и добавьте зелень."
        ],
        macros: { calories: 500, protein: 36, fat: 14, carbs: 54 }
      },
      {
        type: "dinner",
        label: "Ужин",
        title: "Рыбные котлеты с салатом",
        description: "Рыба в домашнем формате без сложной подготовки.",
        prepTime: "35 минут",
        difficulty: "средне",
        tags: ["полезно", "сытно"],
        cookMethod: "Запекать котлеты 20 минут при 180 градусах.",
        ingredients: ["филе белой рыбы", "яйцо", "лук", "капуста", "огурец"],
        steps: [
          "Измельчите рыбу с луком.",
          "Добавьте яйцо и сформируйте котлеты.",
          "Запеките и подайте с салатом."
        ],
        macros: { calories: 460, protein: 38, fat: 18, carbs: 32 }
      }
    ]
  },
  {
    id: "friday",
    title: "Пятница",
    subtitle: "Сытный обед и лёгкий ужин перед выходными.",
    meals: [
      {
        type: "breakfast",
        label: "Завтрак",
        title: "Творог с бананом и йогуртом",
        description: "Без готовки, если утром мало времени.",
        prepTime: "5 минут",
        difficulty: "легко",
        tags: ["быстро", "полезно"],
        cookMethod: "Смешать в миске и подать охлаждённым.",
        ingredients: ["творог", "банан", "йогурт", "корица"],
        steps: [
          "Разомните банан.",
          "Смешайте с творогом и йогуртом.",
          "Добавьте корицу по вкусу."
        ],
        macros: { calories: 350, protein: 26, fat: 10, carbs: 42 }
      },
      {
        type: "lunch",
        label: "Обед",
        title: "Тушёная говядина с картофелем",
        description: "Домашнее блюдо, которое удобно готовить с запасом.",
        prepTime: "80 минут",
        difficulty: "средне",
        tags: ["сытно", "можно приготовить заранее"],
        cookMethod: "Тушить под крышкой 60-70 минут на слабом огне.",
        ingredients: ["говядина", "картофель", "лук", "морковь", "зелень"],
        steps: [
          "Обжарьте говядину до лёгкой корочки.",
          "Добавьте овощи и немного воды.",
          "Тушите до мягкости мяса."
        ],
        macros: { calories: 690, protein: 42, fat: 28, carbs: 62 }
      },
      {
        type: "dinner",
        label: "Ужин",
        title: "Салат с курицей и фасолью",
        description: "Белковый ужин без тяжёлого гарнира.",
        prepTime: "20 минут",
        difficulty: "легко",
        tags: ["быстро", "полезно"],
        cookMethod: "Курицу отварить или использовать запечённую заранее.",
        ingredients: ["курица", "фасоль", "листовой салат", "помидор", "йогурт"],
        steps: [
          "Нарежьте готовую курицу.",
          "Смешайте с фасолью и овощами.",
          "Заправьте йогуртом и специями."
        ],
        macros: { calories: 470, protein: 40, fat: 14, carbs: 42 }
      }
    ]
  },
  {
    id: "saturday",
    title: "Суббота",
    subtitle: "Домашний завтрак и блюда для спокойного дня.",
    meals: [
      {
        type: "breakfast",
        label: "Завтрак",
        title: "Драники с йогуртовым соусом",
        description: "Любимое блюдо в более лёгком варианте.",
        prepTime: "30 минут",
        difficulty: "средне",
        tags: ["сытно"],
        cookMethod: "Готовить на сковороде с минимумом масла по 3 минуты с каждой стороны.",
        ingredients: ["картофель", "яйцо", "мука", "йогурт", "чеснок"],
        steps: [
          "Натрите картофель и отожмите лишнюю жидкость.",
          "Добавьте яйцо и немного муки.",
          "Обжарьте и подайте с йогуртовым соусом."
        ],
        macros: { calories: 520, protein: 16, fat: 20, carbs: 70 }
      },
      {
        type: "lunch",
        label: "Обед",
        title: "Свинина с овощным рагу",
        description: "Сытно, но без тяжёлого соуса и остроты.",
        prepTime: "55 минут",
        difficulty: "средне",
        tags: ["сытно"],
        cookMethod: "Тушить свинину и овощи 35-40 минут.",
        ingredients: ["нежирная свинина", "кабачок", "капуста", "помидор", "зелень"],
        steps: [
          "Нарежьте мясо небольшими кусочками.",
          "Добавьте овощи и тушите под крышкой.",
          "Подавайте с зеленью."
        ],
        macros: { calories: 650, protein: 38, fat: 34, carbs: 42 }
      },
      {
        type: "dinner",
        label: "Ужин",
        title: "Гречка с грибами и салатом",
        description: "Простой ужин без мяса для разнообразия недели.",
        prepTime: "25 минут",
        difficulty: "легко",
        tags: ["полезно", "быстро"],
        cookMethod: "Грибы тушить 10 минут, гречку разогреть или отварить.",
        ingredients: ["гречка", "шампиньоны", "лук", "огурец", "зелень"],
        steps: [
          "Отварите гречку.",
          "Потушите грибы с луком.",
          "Добавьте салат из огурца и зелени."
        ],
        macros: { calories: 450, protein: 18, fat: 12, carbs: 68 }
      }
    ]
  },
  {
    id: "sunday",
    title: "Воскресенье",
    subtitle: "Уютные блюда и заготовки на новую неделю.",
    meals: [
      {
        type: "breakfast",
        label: "Завтрак",
        title: "Запеканка из творога",
        description: "Можно приготовить заранее и есть тёплой или холодной.",
        prepTime: "45 минут",
        difficulty: "легко",
        tags: ["можно приготовить заранее", "сытно"],
        cookMethod: "Запекать 30-35 минут при 180 градусах.",
        ingredients: ["творог", "яйцо", "мука", "йогурт", "ягоды"],
        steps: [
          "Смешайте творог, яйцо и немного муки.",
          "Выложите в форму и добавьте ягоды.",
          "Запеките до золотистой верхушки."
        ],
        macros: { calories: 430, protein: 30, fat: 14, carbs: 44 }
      },
      {
        type: "lunch",
        label: "Обед",
        title: "Куриные тефтели с рисом",
        description: "Мягкое блюдо, которое удобно оставить на понедельник.",
        prepTime: "50 минут",
        difficulty: "средне",
        tags: ["можно приготовить заранее", "сытно"],
        cookMethod: "Тушить тефтели в томатном соусе 25 минут.",
        ingredients: ["куриный фарш", "рис", "томатная паста", "морковь", "зелень"],
        steps: [
          "Смешайте фарш с частью отварного риса.",
          "Сформируйте тефтели.",
          "Потушите в мягком томатном соусе."
        ],
        macros: { calories: 640, protein: 42, fat: 18, carbs: 74 }
      },
      {
        type: "dinner",
        label: "Ужин",
        title: "Овощной салат с рыбой",
        description: "Лёгкий ужин перед новой неделей.",
        prepTime: "20 минут",
        difficulty: "легко",
        tags: ["быстро", "полезно"],
        cookMethod: "Рыбу запечь заранее или приготовить на сковороде 8-10 минут.",
        ingredients: ["филе рыбы", "листовой салат", "огурец", "помидор", "йогурт"],
        steps: [
          "Приготовьте рыбу до готовности.",
          "Нарежьте овощи.",
          "Соедините с рыбой и лёгкой йогуртовой заправкой."
        ],
        macros: { calories: 430, protein: 36, fat: 16, carbs: 34 }
      }
    ]
  }
];

function isMealType(value: unknown): value is MealType {
  return value === "breakfast" || value === "lunch" || value === "dinner";
}

function normalizeGeneratedMenu(value: unknown[]): DayMenu[] | null {
  const normalized = value
    .map((day): DayMenu | null => {
      if (!day || typeof day !== "object") {
        return null;
      }
      const candidate = day as Record<string, unknown>;
      const meals = Array.isArray(candidate.meals) ? candidate.meals : [];
      const normalizedMeals = meals
        .map((meal): Meal | null => {
          if (!meal || typeof meal !== "object") {
            return null;
          }
          const item = meal as Record<string, unknown>;
          const type = item.type;
          const macros =
            item.macros && typeof item.macros === "object"
              ? (item.macros as Record<string, unknown>)
              : {};

          if (!isMealType(type)) {
            return null;
          }

          return {
            type,
            label:
              typeof item.label === "string" ? item.label : mealLabels[type],
            title: typeof item.title === "string" ? item.title : "Блюдо",
            description:
              typeof item.description === "string" ? item.description : "",
            prepTime:
              typeof item.prepTime === "string" ? item.prepTime : "30 минут",
            difficulty:
              item.difficulty === "средне" || item.difficulty === "легко"
                ? item.difficulty
                : "легко",
            tags: Array.isArray(item.tags) ? item.tags.map(String) : [],
            cookMethod:
              typeof item.cookMethod === "string" ? item.cookMethod : "",
            ingredients: Array.isArray(item.ingredients)
              ? item.ingredients.map(String)
              : [],
            steps: Array.isArray(item.steps) ? item.steps.map(String) : [],
            macros: {
              calories: Number(macros.calories) || 0,
              protein: Number(macros.protein) || 0,
              fat: Number(macros.fat) || 0,
              carbs: Number(macros.carbs) || 0
            }
          };
        })
        .filter((meal): meal is Meal => meal !== null);

      if (normalizedMeals.length !== 3) {
        return null;
      }

      return {
        id: typeof candidate.id === "string" ? candidate.id : crypto.randomUUID(),
        title: typeof candidate.title === "string" ? candidate.title : "День",
        subtitle:
          typeof candidate.subtitle === "string" ? candidate.subtitle : "",
        meals: normalizedMeals
      };
    })
    .filter((day): day is DayMenu => day !== null);

  return normalized.length === 7 ? normalized : null;
}

const shoppingList: ShoppingCategory[] = [
  {
    title: "Мясо и птица",
    icon: "🍗",
    items: [
      "куриное филе — 1,2 кг",
      "индейка — 500 г",
      "говядина — 900 г",
      "нежирная свинина — 500 г",
      "куриный фарш — 500 г"
    ]
  },
  {
    title: "Рыба",
    icon: "🐟",
    items: ["минтай или хек — 1 кг", "филе белой рыбы — 700 г"]
  },
  {
    title: "Молочные продукты",
    icon: "🥛",
    items: [
      "творог — 1,2 кг",
      "натуральный йогурт — 1 л",
      "творожный сыр — 200 г",
      "сыр — 200 г",
      "молоко — 1 л"
    ]
  },
  {
    title: "Овощи и зелень",
    icon: "🥦",
    items: [
      "помидоры — 1,5 кг",
      "огурцы — 1 кг",
      "капуста — 1 кочан",
      "кабачки — 3 шт.",
      "болгарский перец — 3 шт.",
      "листовой салат — 2 упаковки",
      "зелень — 3 пучка",
      "шампиньоны — 400 г"
    ]
  },
  {
    title: "Фрукты",
    icon: "🍎",
    items: ["яблоки — 5 шт.", "бананы — 4 шт.", "ягоды — 400 г", "лимон — 1 шт."]
  },
  {
    title: "Крупы и гарниры",
    icon: "🍚",
    items: ["зелёный горошек — 300 г", "фасоль консервированная — 2 банки"]
  },
  {
    title: "Хлеб и выпечка",
    icon: "🍞",
    items: ["цельнозерновой хлеб — 1 упаковка"]
  },
  {
    title: "Дополнительные продукты",
    icon: "🧂",
    items: ["томатная паста — 1 банка", "корица — 1 упаковка"]
  }
];

function summarizeMacros(meals: Meal[]) {
  return meals.reduce(
    (summary, meal) => ({
      calories: summary.calories + meal.macros.calories,
      protein: summary.protein + meal.macros.protein,
      fat: summary.fat + meal.macros.fat,
      carbs: summary.carbs + meal.macros.carbs
    }),
    { calories: 0, protein: 0, fat: 0, carbs: 0 }
  );
}

function HealthContextNote({ profile, complaints }: NutritionPlannerProps) {
  const latestComplaint = complaints[0];
  const hasHealthData = Boolean(
    profile.diabetes_status ||
      profile.cardiovascular_status ||
      profile.allergies ||
      profile.medications ||
      latestComplaint
  );

  if (!hasHealthData) {
    return (
      <details className="nutrition-health-note">
        <summary>
          <strong>Учитываем профиль здоровья</strong>
          <span className="health-chevron">⌄</span>
        </summary>
        <p>
          Заполните анкету и добавьте обращения, чтобы меню было проще
          адаптировать под ваши ограничения.
        </p>
      </details>
    );
  }

  return (
    <details className="nutrition-health-note">
      <summary>
        <strong>Учитываем профиль здоровья</strong>
        <span className="health-chevron">⌄</span>
      </summary>
      <p>
        {[
          profile.diabetes_status && `диабет: ${profile.diabetes_status}`,
          profile.cardiovascular_status &&
            `ССС: ${profile.cardiovascular_status}`,
          profile.allergies && `аллергии: ${profile.allergies}`,
          latestComplaint && `последнее обращение: ${latestComplaint.symptoms}`
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
    </details>
  );
}

function MacroCard({ label, value, unit }: { label: string; value: number; unit: string }) {
  return (
    <div className="nutrition-stat">
      <div className="stat-circle calories">{value}</div>
      <div className="stat-title">{label}</div>
      <div className="stat-subtitle">{unit}</div>
    </div>
  );
}

function MealCard({ meal }: { meal: Meal }) {
  return (
    <article className="nutrition-meal-card">
      <div className="meal-card-top">
        <span className={`meal-type meal-type-${meal.type}`}>{meal.label}</span>
        <span className="meal-difficulty">{meal.difficulty}</span>
      </div>
      <h3>{meal.title}</h3>
      <p>{meal.description}</p>
      <div className="meal-meta">
        <span>⏱ {meal.prepTime}</span>
        <span>{meal.cookMethod}</span>
      </div>
      <div className="nutrition-tags">
        {meal.tags.map((tag) => (
          <span key={tag}>{tag}</span>
        ))}
      </div>
      <div className="meal-macros">
        <span>{meal.macros.calories} ккал</span>
        <span>Б {meal.macros.protein} г</span>
        <span>Ж {meal.macros.fat} г</span>
        <span>У {meal.macros.carbs} г</span>
      </div>
      <details className="recipe-details">
        <summary>Развернуть рецепт</summary>
        <div className="recipe-content">
          <div>
            <h4>Ингредиенты</h4>
            <ul>
              {meal.ingredients.map((ingredient) => (
                <li key={ingredient}>{ingredient}</li>
              ))}
            </ul>
          </div>
          <div>
            <h4>Пошагово</h4>
            <ol>
              {meal.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>
        </div>
      </details>
    </article>
  );
}

export function NutritionPlanner({ profile, complaints }: NutritionPlannerProps) {
  const [menu, setMenu] = useState<DayMenu[]>(weekMenu);
  const [view, setView] = useState<NutritionView>("home");
  const [selectedDayId, setSelectedDayId] = useState(weekMenu[0].id);
  const [mealFilter, setMealFilter] = useState<MealType | "all">("all");
  const [checkedShopping, setCheckedShopping] = useState<Record<string, boolean>>({});
  const [missingPantry, setMissingPantry] = useState<Record<string, boolean>>({});
  const [isRefreshingMenu, setIsRefreshingMenu] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState("");
  const [includeMedicalRecommendations, setIncludeMedicalRecommendations] =
    useState(false);

  const selectedDay =
    menu.find((day) => day.id === selectedDayId) ?? menu[0] ?? weekMenu[0];

  const filteredMeals = selectedDay.meals.filter(
    (meal) => mealFilter === "all" || meal.type === mealFilter
  );

  const selectedDayMacros = useMemo(
    () => summarizeMacros(selectedDay.meals),
    [selectedDay]
  );

  function openDay(dayId: string) {
    setSelectedDayId(dayId);
    setView("day");
  }

  async function refreshWeeklyMenu() {
    setIsRefreshingMenu(true);
    setRefreshMessage("Обновляем меню через ИИ-нутрициолога...");

    try {
      const response = await generateNutritionMenu(
        pantryItems,
        includeMedicalRecommendations
      );
      const generatedMenu = normalizeGeneratedMenu(response.menu);

      if (response.ai_status === "completed" && generatedMenu) {
        setMenu(generatedMenu);
        setSelectedDayId(generatedMenu[0].id);
        setRefreshMessage(response.message || "Меню на неделю обновлено.");
        return;
      }

      setRefreshMessage(
        response.message || "ИИ не вернул меню в подходящем формате."
      );
    } catch (error) {
      setRefreshMessage(
        error instanceof Error
          ? error.message
          : "Не удалось обновить меню. Попробуйте ещё раз."
      );
    } finally {
      setIsRefreshingMenu(false);
    }
  }

  function renderHome() {
    return (
      <>
        <div className="nutrition-hero">
          <h2>AI-меню на неделю</h2>
          <p>План питания, рецепты и список покупок в одном месте</p>
        </div>
        <HealthContextNote profile={profile} complaints={complaints} />
        <label className="nutrition-consent-card">
          <input
            type="checkbox"
            checked={includeMedicalRecommendations}
            onChange={(event) =>
              setIncludeMedicalRecommendations(event.target.checked)
            }
          />
          <span>
            <strong>Разрешаю учесть рекомендации медконсультанта</strong>
            <small>
              Нутрициолог адаптирует меню под тактику, ограничения и
              рекомендации из последних консультаций.
            </small>
          </span>
        </label>
        <div className="nutrition-intro-card">
          <p>
            Выбирай день недели, смотри блюда, рецепты и продукты, которые
            нужно купить. Меню простое, домашнее и без экзотических продуктов.
          </p>
        </div>
        <div className="nutrition-actions">
          {menu.map((day) => (
            <button
              key={day.id}
              className="nutrition-day-button"
              type="button"
              onClick={() => openDay(day.id)}
            >
              <span className="day-icon">
                {dayShortLabels[day.id]?.icon ?? "🍽️"}
              </span>
              <span>{dayShortLabels[day.id]?.label ?? day.title.slice(0, 2)}</span>
              <small>{day.title}</small>
            </button>
          ))}
        </div>
        <div className="nutrition-main-buttons">
          <button
            className="nutrition-refresh-button"
            type="button"
            disabled={isRefreshingMenu}
            onClick={() => void refreshWeeklyMenu()}
          >
            🔄 {isRefreshingMenu ? "Обновляем меню..." : "Обновить меню"}
          </button>
          <button type="button" onClick={() => setView("shopping")}>
            🛒 Список продуктов
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setView("pantry")}
          >
            🏠 Продукты дома
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setView("week")}
          >
            📋 Показать всё меню
          </button>
        </div>
        {refreshMessage && (
          <div className="nutrition-refresh-message">{refreshMessage}</div>
        )}
      </>
    );
  }

  function renderDay() {
    return (
      <div className="nutrition-day-view">
        <div className="nutrition-view-header">
          <div>
            <h2>{selectedDay.title}</h2>
            <p>{selectedDay.subtitle}</p>
          </div>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setView("home")}
          >
            ← На главную
          </button>
        </div>
        <div className="day-macro-strip nutrition-stats">
          <MacroCard label="Калории" value={selectedDayMacros.calories} unit="ккал/день" />
          <MacroCard label="Белки" value={selectedDayMacros.protein} unit="г" />
          <MacroCard label="Жиры" value={selectedDayMacros.fat} unit="г" />
          <MacroCard label="Углеводы" value={selectedDayMacros.carbs} unit="г" />
        </div>
        <div className="meal-filter">
          {(["all", "breakfast", "lunch", "dinner"] as const).map((filter) => (
            <button
              key={filter}
              className={mealFilter === filter ? "is-active" : ""}
              type="button"
              onClick={() => setMealFilter(filter)}
            >
              {filter === "all" ? "Все" : mealLabels[filter]}
            </button>
          ))}
        </div>
        <div className="nutrition-meal-grid">
          {filteredMeals.map((meal) => (
            <MealCard key={meal.type} meal={meal} />
          ))}
        </div>
      </div>
    );
  }

  function renderShopping() {
    return (
      <div className="nutrition-list-view">
        <div className="nutrition-view-header">
          <div>
            <h2>Список покупок</h2>
            <p>Не включаем продукты, которые уже есть дома.</p>
          </div>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setView("home")}
          >
            ← На главную
          </button>
        </div>
        <div className="shopping-grid">
          {shoppingList.map((category) => (
            <article className="shopping-category" key={category.title}>
              <h3>
                <span>{category.icon}</span>
                {category.title}
              </h3>
              {category.items.map((item) => (
                <label className="check-row" key={item}>
                  <input
                    checked={Boolean(checkedShopping[item])}
                    type="checkbox"
                    onChange={(event) =>
                      setCheckedShopping({
                        ...checkedShopping,
                        [item]: event.target.checked
                      })
                    }
                  />
                  <span>{item}</span>
                </label>
              ))}
            </article>
          ))}
        </div>
      </div>
    );
  }

  function renderPantry() {
    return (
      <div className="nutrition-list-view">
        <div className="nutrition-view-header">
          <div>
            <h2>Продукты дома</h2>
            <p>Отметьте, что закончилось, чтобы докупить позже.</p>
          </div>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setView("home")}
          >
            ← На главную
          </button>
        </div>
        <div className="pantry-tags">
          {pantryItems.map((item) => (
            <label
              className={`pantry-tag ${missingPantry[item] ? "is-missing" : ""}`}
              key={item}
            >
              <input
                checked={Boolean(missingPantry[item])}
                type="checkbox"
                onChange={(event) =>
                  setMissingPantry({
                    ...missingPantry,
                    [item]: event.target.checked
                  })
                }
              />
              <span>{item}</span>
            </label>
          ))}
        </div>
      </div>
    );
  }

  function renderWeek() {
    return (
      <div className="nutrition-list-view">
        <div className="nutrition-view-header">
          <div>
            <h2>Меню на всю неделю</h2>
            <p>Краткий обзор без рецептов.</p>
          </div>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setView("home")}
          >
            ← На главную
          </button>
        </div>
        <div className="week-overview">
          {menu.map((day) => (
            <article key={day.id} className="week-day-card">
              <h3>{day.title}</h3>
              {day.meals.map((meal) => (
                <p key={meal.type}>
                  <strong>{meal.label}:</strong> {meal.title}
                </p>
              ))}
              <button
                className="secondary-button"
                type="button"
                onClick={() => openDay(day.id)}
              >
                Открыть день
              </button>
            </article>
          ))}
        </div>
      </div>
    );
  }

  return (
    <section className="nutrition-planner">
      {view === "home" && renderHome()}
      {view === "day" && renderDay()}
      {view === "shopping" && renderShopping()}
      {view === "pantry" && renderPantry()}
      {view === "week" && renderWeek()}
    </section>
  );
}
