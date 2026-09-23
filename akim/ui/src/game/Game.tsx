import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check, FileDown, HelpCircle, Link2, MapPin, Route, Save, Sparkles, X } from "lucide-react";
import MobilityPanel, { useMobility } from "../MobilityPanel";
import ComplaintPanel from "../ComplaintPanel";
import type { ComplaintCollection, Complaint } from "../complaints";
import CityMap, { type Marker } from "../CityMap";
import AskPanel from "../AskPanel";
import AkimPanel from "../AkimPanel";
import CityDataPanel from "../CityDataPanel";
import ResidentCard from "../ResidentCard";
import { directions, districts, samplePlan, type Choice, type Direction, type DistrictId } from "../data";
import { baseline, projectEffects, simulate, validate } from "../engine";
import { examples, pollProposal, type Poll } from "../residents";
import { population, type Resident } from "../population";
import { useServices } from "../services";
import Report from "../planner/Report";
import LeadershipMemo from "../planner/LeadershipMemo";
import { type ComparisonTarget } from "../planner/Comparison";
import {
  criticalCells,
  decodePlan,
  districtName,
  encodePlan,
  fmt,
  inDistrict,
  lower,
  weakestDistrict,
} from "../planner/analysis";
import { indicatorNames } from "../data";
import DistrictPanel from "./DistrictPanel";
import Tray from "./Tray";
import Variants from "./VariantsDialog";
import { parseVariants, serializeVariants, VARIANT_IDS, VARIANTS_STORAGE, type Variant } from "./variants";
import { reaction, shortNames } from "./labels";
import "../planner/planner-sheet.css";
import "./game.css";

type Stage = "intro" | "brief" | "turn" | "report";
type Dialog = "ask" | "akim" | "about" | "data" | "variants" | "mobility" | "complaints" | null;

const STORAGE = "sim-astana-game-v1";

function readInitial() {
  const params = new URLSearchParams(window.location.search);
  let plan = decodePlan(params.get("plan"));
  let priorities = (params.get("focus") ?? "")
    .split(",")
    .filter((d): d is Direction => (directions as readonly string[]).includes(d))
    .slice(0, 2);
  if (!plan.length && !params.has("plan")) {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE) ?? "null");
      if (saved && typeof saved.plan === "string") {
        plan = decodePlan(saved.plan);
        priorities = Array.isArray(saved.priorities) ? saved.priorities : [];
      }
    } catch {
      /* Storage unavailable; start clean. */
    }
  }
  const versus = decodePlan(params.get("vs"));
  const comparison: ComparisonTarget | null = versus.length === 5 && !validate(versus).length
    ? { name: "Вариант из ссылки", plan: versus }
    : null;
  const stage: Stage =
    (params.get("step") === "report" || !!comparison) && plan.length === 5 && validate(plan).length === 0
      ? "report"
      : plan.length
        ? "turn"
        : "intro";
  return { plan, priorities, stage, comparison };
}

export default function Game() {
  const { city } = useServices();
  const initial = useRef(readInitial()).current;
  const [stage, setStage] = useState<Stage>(initial.stage);
  const [plan, setPlan] = useState<Choice[]>(initial.plan);
  const [priorities, setPriorities] = useState<Direction[]>(initial.priorities);
  const [selected, setSelected] = useState<DistrictId | null>(null);
  const [resident, setResident] = useState<Resident | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [askQuestion, setAskQuestion] = useState("");
  const [livePoll, setLivePoll] = useState<Poll | null>(null);
  const [toast, setToast] = useState("");
  const [minutes, setMinutes] = useState(540);
  const [copied, setCopied] = useState(false);
  const [comparison, setComparison] = useState<ComparisonTarget | null>(initial.comparison);
  const [variants, setVariants] = useState<Variant[]>(() => {
    try {
      return parseVariants(localStorage.getItem(VARIANTS_STORAGE));
    } catch {
      return [];
    }
  });

  const [mobilityAfter, setMobilityAfter] = useState(true);
  const [replaying, setReplaying] = useState(false);
  const [complaints, setComplaints] = useState<ComplaintCollection | null>(null);
  const [complaintFilter, setComplaintFilter] = useState<Direction | "">("");
  const [complaintFocus, setComplaintFocus] = useState<Complaint | null>(null);
  const [complaintVisible, setComplaintVisible] = useState(false);
  const mappedComplaints = useMemo(() => complaintVisible
    ? (complaints?.posts ?? []).filter(p => p.decision === "accepted" && (!complaintFilter || p.directions.includes(complaintFilter)))
    : [], [complaints, complaintVisible, complaintFilter]);
  const mobility = useMobility(plan, dialog === "mobility");
  const mobilityPhase = dialog === "mobility" && mobility.data
    ? mobilityAfter ? mobility.data.after : mobility.data.before : null;
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/complaints", { signal: controller.signal })
      .then(r => r.ok ? r.json() : null)
      .then(r => { if (r?.collection) setComplaints(r.collection); })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  // The city keeps moving at a fixed, unobtrusive pace; there are no clock controls.
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced && !replaying) return;
    let last = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const elapsed = Math.min(1, (now - last) / 1000);
      last = now;
      if (!document.hidden) setMinutes((t) => (t + elapsed * (dialog === "mobility" ? 36 : 4)) % 1440);
    }, 100);
    return () => clearInterval(timer);
  }, [dialog, replaying]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (plan.length) params.set("plan", encodePlan(plan));
    if (comparison) params.set("vs", encodePlan(comparison.plan));
    if (priorities.length) params.set("focus", priorities.join(","));
    if (stage === "report") params.set("step", "report");
    const query = params.toString();
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
    try {
      localStorage.setItem(STORAGE, JSON.stringify({ plan: encodePlan(plan), priorities }));
    } catch {
      /* Storage unavailable; the URL still carries the scenario. */
    }
  }, [plan, priorities, stage, comparison]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (dialog) setDialog(null);
      else if (resident) setResident(null);
      else if (stage === "report") setStage("turn");
      else setSelected(null);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [dialog, resident, stage]);

  const errors = validate(plan);
  const projection = projectEffects(plan);
  const result = plan.length === 5 && !errors.length ? simulate(plan).result : null;
  // Residents colour themselves by the local model after every decision; a live poll overrides it.
  const poll = useMemo(() => livePoll ?? (plan.length ? pollProposal(plan, "Мой план") : null), [livePoll, plan]);
  const markers: Marker[] = plan.map((c) => ({
    id: c.measureId,
    districtId: c.districtId ?? null,
    label: shortNames[c.measureId],
  }));
  const weakest = weakestDistrict(baseline);
  const critical = criticalCells(baseline);
  const weather = city?.weather.data;
  const stayInside = !!weather && (weather.temperature < -10 || weather.wind > 40 || weather.code >= 51);

  const changePlan = (next: Choice[]) => {
    setPlan(next);
    setLivePoll(null);
  };
  const add = (choice: Choice) => {
    const gain = projectEffects([...plan, choice]).score - projection.score;
    changePlan([...plan, choice]);
    setToast(reaction(choice, gain));
  };
  const remove = (measureId: string) => changePlan(plan.filter((c) => c.measureId !== measureId));
  const persistVariants = (next: Variant[]) => {
    try {
      localStorage.setItem(VARIANTS_STORAGE, serializeVariants(next));
      setVariants(next);
      return true;
    } catch {
      return false;
    }
  };
  const compareVariant = (variant: Variant) => {
    setComparison({ name: variant.name, plan: variant.plan, variantId: variant.id });
  };
  const saveVariant = () => {
    if (!result) return;
    const id = VARIANT_IDS.find((key) => !variants.some((v) => v.id === key));
    if (!id) return;
    const variant: Variant = { id, name: `Вариант ${id}`, plan: plan.map((c) => ({ ...c })) };
    if (!persistVariants([...variants, variant])) {
      setToast("Не удалось сохранить вариант: хранилище браузера недоступно.");
      return;
    }
    compareVariant(variant);
    setToast(`Сохранён как ${variant.name}`);
  };
  const start = () => {
    setStage("turn");
    setSelected(null);
  };
  const openAsk = (question: string) => {
    setAskQuestion(question);
    setDialog("ask");
  };
  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setCopied(false);
    }
  };

  const togglePriority = (d: Direction) =>
    setPriorities((p) => (p.includes(d) ? p.filter((x) => x !== d) : [...p, d].slice(-2)));

  return (
    <main className={`app game stage-${stage} ${dialog ? "has-panel" : ""}`}>
      <CityMap
        mobility={mobilityPhase}
        complaints={mappedComplaints}
        complaintFocus={complaintFocus}
        minutes={minutes}
        residentId={resident?.id ?? null}
        stayInside={stayInside}
        onResident={(person) => {
          if (stage === "intro" || stage === "brief") return;
          setResident(person);
          setSelected(person.districtId);
        }}
        selected={stage === "turn" ? selected : null}
        onSelect={(id) => {
          if (stage === "intro") return;
          if (stage === "brief") setStage("turn");
          setResident(null);
          setSelected(id);
        }}
        result={result ?? (plan.length ? projection : null)}
        after={dialog !== "mobility" || mobilityAfter}
        poll={poll}
        panelOpen={stage === "turn" && !!selected}
        markers={markers}
        spotlight={stage === "brief" || (stage === "turn" && !plan.length) ? weakest.id : null}
      />

      <header className="game-top">
        <div className="game-brand">
          <b>Аким на 5 часов</b>
          <span>Астана, синтетическая модель</span>
        </div>
        {stage !== "intro" && (
          <div className="game-steps" aria-label="Шаги">
            <span className={stage === "brief" ? "current" : "done"}>Задача</span>
            <span className={stage === "turn" ? "current" : plan.length === 5 ? "done" : ""}>
              Решения {plan.length}/5
            </span>
            <span className={stage === "report" ? "current" : ""}>Итог</span>
          </div>
        )}
        <div className="game-tools">
          <button type="button" className="text-button" onClick={() => { setDialog("mobility"); setMinutes(480); }}>
            <Route size={14} /> Мобильность
          </button>
          <button type="button" className="text-button" onClick={() => { setDialog("complaints"); setComplaintVisible(true); }}>
            <MapPin size={14} /> Жалобы
          </button>
          {complaintVisible && <button type="button" className="icon-button" aria-label="Скрыть пины жалоб" onClick={() => { setComplaintVisible(false); setComplaintFocus(null); }}><X size={14} /></button>}
          <button type="button" className="text-button" onClick={() => setDialog("variants")}>
            Варианты ({fmt(variants.length, 0)})
          </button>
          <button type="button" className="text-button" onClick={() => setDialog("data")}>
            Данные города
          </button>
          <button type="button" className="text-button" onClick={() => setDialog("about")}>
            <HelpCircle size={14} /> Как это работает
          </button>
        </div>
      </header>

      {stage === "intro" && !dialog && (
        <section className="intro glass" aria-labelledby="intro-title">
          <h1 id="intro-title">Пять решений для города</h1>
          <p>
            У вас бюджет 100 у.е. и 2 000 жителей в пяти районах. Выберите пять мер так, чтобы
            качество жизни выросло и ни один район не остался позади.
          </p>
          <button type="button" className="cta" onClick={() => setStage("brief")}>
            Стать акимом <ArrowRight size={17} />
          </button>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              changePlan(samplePlan.map((c) => ({ ...c })));
              setStage("report");
            }}
          >
            Посмотреть готовый пример
          </button>
        </section>
      )}

      {stage === "brief" && !dialog && (
        <section className="briefing glass" aria-labelledby="brief-title">
          <h1 id="brief-title">Город сейчас: {fmt(baseline.score)} из 100</h1>
          <ul className="briefing-facts">
            <li>
              <b>70%</b> балла даёт средний район, <b>30%</b> — самый слабый. Сейчас это{" "}
              {districtName(weakest.id)}, {fmt(weakest.score, 1)}.
            </li>
            <li>
              <b>−1</b> за каждый показатель ниже 40. Их {critical.length}:{" "}
              {critical.map((c) => `${lower(indicatorNames[c.indicator])} ${inDistrict(c.district)}`).join(", ")}.
            </li>
            <li>
              <b>5</b> решений, не больше двух на направление, <b>100 у.е.</b> на всё.
            </li>
          </ul>
          <p className="briefing-focus">Что для вас главное? Необязательно, до двух направлений.</p>
          <div className="briefing-options">
            {directions.map((d) => (
              <button key={d} type="button" aria-pressed={priorities.includes(d)} onClick={() => togglePriority(d)}>
                {d}
              </button>
            ))}
          </div>
          <div className="briefing-actions">
            <button type="button" className="cta" onClick={start}>
              Начать: район {districtName(weakest.id)} <ArrowRight size={17} />
            </button>
            <button type="button" className="text-button" onClick={() => setDialog("akim")}>
              <Sparkles size={14} /> Поручить AI-акиму
            </button>
          </div>
        </section>
      )}

      {stage === "turn" && selected && !resident && !dialog && (
        <DistrictPanel
          key={selected}
          districtId={selected}
          plan={plan}
          projection={projection}
          onAdd={add}
          onClose={() => setSelected(null)}
          onAsk={() => openAsk(plan.length ? examples[2] : examples[0])}
          onJump={(id) => {
            setResident(null);
            setSelected(id);
          }}
        />
      )}

      {stage === "turn" && !selected && !resident && !dialog && (
        <div className="turn-hint glass" role="status">
          {plan.length
            ? plan.length === 5
              ? "Пять решений приняты. Подведите итог или замените решение в корзине."
              : "Нажмите на район на карте, чтобы добавить следующее решение."
            : `Нажмите на район ${districtName(weakest.id)} на карте: он самый слабый.`}
        </div>
      )}

      {resident && !dialog && stage === "turn" && (
        <ResidentCard
          resident={resident}
          minutes={minutes}
          poll={poll}
          stayInside={stayInside}
          onClose={() => setResident(null)}
        />
      )}

      {(stage === "turn" || stage === "report") && dialog !== "mobility" && dialog !== "complaints" && (
        <Tray
          plan={plan}
          score={projection.score}
          errors={errors}
          onRemove={(id) => {
            remove(id);
            if (stage === "report") setStage("turn");
          }}
          onReport={() => setStage("report")}
        />
      )}

      {result && <LeadershipMemo plan={plan} priorities={priorities} />}

      {stage === "report" && result && (
        <div className="sheet-backdrop" hidden={!!dialog} onClick={() => setStage("turn")}>
          <section
            className="sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sheet-bar">
              <div className="sheet-actions">
                <button type="button" className="secondary" onClick={saveVariant} disabled={variants.length >= 3} title={variants.length >= 3 ? "Сохранено максимум 3 варианта" : undefined}>
                  <Save size={15} /> Сохранить как вариант
                </button>
                <button type="button" className="secondary" onClick={() => openAsk(examples[2])}>
                  Спросить жителей
                </button>
                <button type="button" className="secondary" onClick={() => setDialog("akim")}>
                  <Sparkles size={15} /> AI-аким
                </button>
                <button type="button" className="secondary" onClick={() => window.print()} title="Откроется печать: выберите «Сохранить как PDF»">
                  <FileDown size={15} /> Скачать записку
                </button>
                <button type="button" className="secondary" onClick={copyLink}>
                  <Link2 size={15} /> {copied ? "Скопировано" : "Ссылка на сценарий"}
                </button>
              </div>
              <button type="button" className="icon-button" onClick={() => setStage("turn")} aria-label="Вернуться к карте">
                <X size={20} />
              </button>
            </div>
            <Report
              plan={plan}
              priorities={priorities}
              comparison={comparison}
              onCompare={setComparison}
              onApply={(next) => {
                changePlan(next);
                setToast("Замена применена. Карта и жители обновлены.");
              }}
              onEdit={() => setStage("turn")}
            />
          </section>
        </div>
      )}

      {dialog === "variants" && (
        <Variants
          variants={variants}
          canCompare={!!result}
          onClose={() => setDialog(null)}
          onLoad={(variant) => {
            changePlan(variant.plan.map((c) => ({ ...c })));
            setSelected(null);
            setResident(null);
            setStage("turn");
            setDialog(null);
            setToast(`Загружен ${variant.name}`);
          }}
          onCompare={(variant) => {
            compareVariant(variant);
            setStage("report");
            setDialog(null);
          }}
          onRename={(id, name) => {
            if (!persistVariants(variants.map((v) => v.id === id ? { ...v, name } : v))) return false;
            if (comparison?.variantId === id) setComparison({ ...comparison, name });
            return true;
          }}
        />
      )}

      {dialog === "ask" && (
        <AskPanel
          plan={plan}
          poll={livePoll}
          onPoll={setLivePoll}
          onClose={() => setDialog(null)}
          initialQuestion={askQuestion}
        />
      )}
      {dialog === "akim" && (
        <AkimPanel
          plan={plan}
          onChange={(next) => {
            changePlan(next);
            setStage("turn");
            setToast("План AI-акима на карте. Проверьте его и подведите итог.");
          }}
          onClose={() => setDialog(null)}
          onBuild={() => {
            setDialog(null);
            setStage("turn");
          }}
        />
      )}
      {dialog === "mobility" && <MobilityPanel
        plan={plan} data={mobility.data} error={mobility.error}
        after={mobilityAfter} onAfter={setMobilityAfter} onClose={() => setDialog(null)}
        onExample={next => { changePlan(next); setStage("turn"); }}
        onReplay={() => { setMinutes(455); setReplaying(true); }}
      />}
      {dialog === "complaints" && <ComplaintPanel
        collection={complaints} filter={complaintFilter} onFilter={setComplaintFilter}
        onCollection={collection => { setComplaints(collection); setComplaintVisible(true); setComplaintFocus(null); }}
        onFocus={complaint => { setComplaintFocus({ ...complaint }); setComplaintVisible(true); }}
        onClose={() => setDialog(null)}
      />}
      {dialog === "data" && <CityDataPanel onClose={() => setDialog(null)} />}
      {dialog === "about" && (
        <section className="about-panel glass" role="dialog" aria-labelledby="about-title">
          <div className="panel-heading">
            <h2 id="about-title">Как это работает</h2>
            <button type="button" className="icon-button" onClick={() => setDialog(null)} aria-label="Закрыть">
              <X size={20} />
            </button>
          </div>
          <p>
            Балл качества жизни считается по правилам задания: 70% — средний балл районов с учётом
            населения, 30% — самый слабый район, минус 1 за каждый показатель ниже 40. Эффект мер
            учитывает задержку запуска и синергии.
          </p>
          <p>
            Жители на карте синтетические: 2 000 профилей с домом, работой и интересами. После
            каждого решения они окрашиваются по тому, помогает оно им или нет. Это модель, а не опрос.
          </p>
          <p>
            AI-аким и вопросы жителям работают через OpenAI, когда на сервере настроен ключ. Числа
            всегда считает модель; AI их только объясняет.
          </p>
          <p>
            Данные о погоде, воздухе, населении и ДТП загружаются из открытых источников и показаны
            для контекста. Карта схематичная, границы приблизительные.
          </p>
        </section>
      )}

      {toast && !dialog && (
        <div className="toast glass" role="status">
          <Check size={16} />
          {toast}
        </div>
      )}
      <p className="game-foot">
        {districts.length} районов, {population.length} жителей. Схематичная карта, границы приблизительные.
      </p>
    </main>
  );
}
