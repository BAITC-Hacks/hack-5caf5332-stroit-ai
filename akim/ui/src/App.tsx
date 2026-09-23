import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  Database,
  Pause,
  Play,
  ArrowLeft,
  ArrowUpRight,
  ChartNoAxesColumnIncreasing,
  Check,
  ChevronRight,
  Compass,
  HelpCircle,
  MapPin,
  MessageCircle,
  Plus,
  SlidersHorizontal,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import CityMap from "./CityMap";
import PlanBuilder, { fmt } from "./PlanBuilder";
import AkimPanel from "./AkimPanel";
import AskPanel from "./AskPanel";
import {
  districts,
  indicatorNames,
  samplePlan,
  type Choice,
  type DistrictId,
} from "./data";
import { baseline, simulate, validate } from "./engine";
import { examples, type Poll } from "./residents";
import "./styles.css";
import CityDataPanel from "./CityDataPanel";
import ResidentCard from "./ResidentCard";
import { useServices } from "./services";
import { population, activityCounts, type Resident } from "./population";
import { money, BUDGET_LIMIT } from "./money";
type Panel = "plan" | "ask" | "akim" | "about" | "data" | null;
function loadPlan(): Choice[] {
  try {
    const raw: unknown = JSON.parse(
      localStorage.getItem("sim-astana-plan-v1") ?? "[]",
    );
    if (
      !Array.isArray(raw) ||
      !raw.every(
        (c) => c && typeof c === "object" && typeof c.measureId === "string",
      )
    )
      return [];
    const plan = raw as Choice[];
    return validate(plan, true).length ? [] : plan;
  } catch {
    return [];
  }
}
export default function App() {
  const { city } = useServices();
  const [minutes, setMinutes] = useState(480);
  const [playing, setPlaying] = useState(
    () => !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [speed, setSpeed] = useState(6);
  const [resident, setResident] = useState<Resident | null>(null);
  const weather = city?.weather.data;
  const stayInside =
    !!weather &&
    (weather.temperature < -10 || weather.wind > 40 || weather.code >= 51);
  const counts = activityCounts(minutes, stayInside);
  const clock =
    `${Math.floor(minutes / 60) % 24}`.padStart(2, "0") +
    ":" +
    `${Math.floor(minutes) % 60}`.padStart(2, "0");
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const elapsed = Math.min(1, (now - last) / 1000);
      last = now;
      if (!document.hidden) setMinutes((t) => (t + elapsed * speed) % 1440);
    }, 100);
    return () => clearInterval(timer);
  }, [playing, speed]);
  const [plan, setPlan] = useState<Choice[]>(loadPlan);
  const [selected, setSelected] = useState<DistrictId | null>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const [after, setAfter] = useState(true);
  const [poll, setPoll] = useState<Poll | null>(null);
  const [initialQuestion, setInitialQuestion] = useState("");
  const [toast, setToast] = useState("");
  const { result } = simulate(plan);
  const currentDistrict = districts.find((d) => d.id === selected);
  const previousFocus = useRef<HTMLElement | null>(null);
  const lastPanel = useRef<Panel>(null);
  const changePlan = (next: Choice[]) => {
    setPlan(next);
    setPoll(null);
    setAfter(true);
    try {
      localStorage.setItem("sim-astana-plan-v1", JSON.stringify(next));
    } catch {
      /* Storage may be unavailable; the session remains usable. */
    }
  };
  const open = (next: Panel) => {
    setToast("");
    setResident(null);
    previousFocus.current = document.activeElement as HTMLElement;
    setPanel(next);
  };
  const close = () => {
    setPanel(null);
    setPoll(null);
    previousFocus.current?.focus();
  };
  const askPlan = () => {
    setInitialQuestion(examples[2]);
    setPoll(null);
    open("ask");
  };
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (panel) {
          setPanel(null);
          setPoll(null);
          previousFocus.current?.focus();
        } else setSelected(null);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [panel]);
  useEffect(() => {
    if (panel && panel !== lastPanel.current) {
      requestAnimationFrame(() => {
        const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
        const el = dialog?.querySelector<HTMLElement>("textarea,button");
        el?.focus();
      });
    }
    lastPanel.current = panel;
  }, [panel]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 4000);
    return () => clearTimeout(timer);
  }, [toast]);
  return (
    <main className={`app ${panel ? "has-panel" : ""}`}>
      <CityMap
        minutes={minutes}
        residentId={resident?.id ?? null}
        stayInside={stayInside}
        onResident={(person) => {
          setResident(person);
          setSelected(person.districtId);
        }}
        selected={selected}
        onSelect={(id) => {
          setSelected(id);
          if (panel === "about") setPanel(null);
        }}
        result={result}
        after={after}
        poll={poll}
        panelOpen={panel === "plan" || panel === "akim"}
      />
      <header className="topbar">
        <div className="brand-block">
          <button
            className="brand glass"
            onClick={() => {
              setSelected(null);
              close();
            }}
            aria-label="Sim Astana — весь город"
          >
            <span className="brand-mark">
              <i />
              <i />
              <i />
            </span>
            <span>
              sim astana<span className="brand-period">.</span>
            </span>
            <span className="brand-tag">ГОРОД В ВАШИХ РУКАХ</span>
          </button>
          <div className="breadcrumb">
            Аким на 5 часов <span>/</span> Астана, Казахстан
          </div>
        </div>
        <div className="city-status glass">
          <span className="live-dot" />
          <div>
            <strong>
              Город живёт <span>·</span> 2 000 жителей
            </strong>
            <small>Синтетическая симуляция</small>
          </div>
          <Users size={19} />
        </div>
      </header>
      <div className="simulation-controls glass" aria-label="Время симуляции">
        <button
          className="icon-button"
          aria-label={playing ? "Пауза симуляции" : "Продолжить симуляцию"}
          onClick={() => setPlaying((p) => !p)}
        >
          {playing ? <Pause size={15} /> : <Play size={15} />}
        </button>
        <time>{clock}</time>
        <select
          aria-label="Скорость симуляции"
          value={speed}
          onChange={(e) => setSpeed(Number(e.target.value))}
        >
          <option value={6}>×6</option>
          <option value={30}>×30</option>
          <option value={120}>×120</option>
        </select>
        <span>{counts.moving} в пути</span>
        <button
          className="icon-button"
          aria-label="Познакомиться с жителем"
          onClick={() => {
            const person = population.find(
              (p) => !selected || p.districtId === selected,
            )!;
            setResident(person);
            setSelected(person.districtId);
          }}
        >
          <Users size={15} />
        </button>
        <button
          className="data-toggle"
          onClick={() => (panel === "data" ? close() : open("data"))}
          aria-label="Открыть реальные данные"
        >
          <Database size={14} />
          {weather ? `${weather.temperature}°` : "Данные"}
          {city?.air.data && <small>AQI {city.air.data.aqi}</small>}
        </button>
      </div>
      {resident && !panel && (
        <ResidentCard
          resident={resident}
          minutes={minutes}
          poll={poll}
          stayInside={stayInside}
          onClose={() => setResident(null)}
        />
      )}
      {selected && (
        <button className="whole-city glass" onClick={() => setSelected(null)}>
          <ArrowLeft size={15} />
          Весь город
        </button>
      )}
      {!panel && !selected && !result && (
        <section className="welcome">
          <div className="eyebrow">
            <span className="tiny-line" />
            МАЛЕНЬКИЙ ГОРОД. БОЛЬШИЕ РЕШЕНИЯ.
          </div>
          <h1>
            А если акимом <br />
            будете <em>вы?</em>
          </h1>
          <p>
            Пять решений. {money(BUDGET_LIMIT)} млн ₸.
            <br />И целый город, который почувствует
            <br />
            каждый ваш выбор.
          </p>
          <button className="welcome-button" onClick={() => open("plan")}>
            Изменить город <ArrowUpRight size={17} />
          </button>
          <button
            className="sample-link"
            onClick={() => {
              changePlan(samplePlan.map((c) => ({ ...c })));
              setToast("Сценарий применён: 5 решений, 20 700 млн ₸.");
            }}
          >
            Попробовать готовый сценарий <ChevronRight size={13} />
          </button>
          <div className="welcome-hint">
            <MapPin size={14} />
            <span>
              Нажмите на район,
              <br />
              чтобы познакомиться с жителями
            </span>
          </div>
        </section>
      )}
      {!panel && currentDistrict && !resident && (
        <section className="district-panel glass">
          <div className="district-title">
            <div>
              <div className="eyebrow">ЗНАКОМСТВО С РАЙОНОМ</div>
              <h2>{currentDistrict.name}</h2>
            </div>
            <button
              className="icon-button"
              onClick={() => setSelected(null)}
              aria-label="Закрыть район"
            >
              <X size={18} />
            </button>
          </div>
          <p>{currentDistrict.description}</p>
          <div className="district-stats">
            <div>
              <small>Исходный балл</small>
              <strong>
                {fmt(baseline.districts.find((d) => d.id === selected)!.score)}
              </strong>
            </div>
            <div>
              <small>Жителей модели</small>
              <strong>{Math.round(currentDistrict.population * 2000)}</strong>
            </div>
          </div>
          <div className="section-label">ГЛАВНЫЕ ПОТРЕБНОСТИ</div>
          {currentDistrict.needs.map((k) => (
            <div className="need" key={k}>
              <span>{indicatorNames[k]}</span>
              <b className={currentDistrict.values[k] < 40 ? "negative" : ""}>
                {currentDistrict.values[k]}
                <small>/100</small>
              </b>
            </div>
          ))}
          <blockquote>
            {currentDistrict.voices[0]}
            <cite>Голос синтетического жителя</cite>
          </blockquote>
          <button className="dark wide" onClick={() => open("plan")}>
            Помочь району <Plus size={15} />
          </button>
        </section>
      )}
      {panel !== "akim" && panel !== "ask" && (
        <aside className={`score-card glass ${result ? "has-result" : ""}`}>
          <div className="score-title">
            <ChartNoAxesColumnIncreasing size={15} />
            <span>КАЧЕСТВО ЖИЗНИ</span>
            <button
              className="icon-button"
              onClick={() => open("about")}
              aria-label="Как считается балл"
            >
              <HelpCircle size={14} />
            </button>
          </div>
          <div className="score-value">
            <strong>{fmt(result ? result.score : baseline.score)}</strong>
            <span>
              {result ? (
                <b>+{fmt(result.score - baseline.score)}</b>
              ) : (
                <>
                  из 100
                  <br />
                  на старте
                </>
              )}
            </span>
          </div>
          <p>
            {result
              ? "Ваши пять решений меняют город"
              : "У каждого решения есть последствия"}
          </p>
          {result && (
            <div className="before-after">
              <button
                className={!after ? "active" : ""}
                onClick={() => setAfter(false)}
                aria-pressed={!after}
              >
                До
              </button>
              <button
                className={after ? "active" : ""}
                onClick={() => setAfter(true)}
                aria-pressed={after}
              >
                После · 2 года
              </button>
            </div>
          )}
        </aside>
      )}
      {result && !panel && !selected && (
        <div className="result-nudge glass">
          <span className="success-icon">
            <Check size={17} />
          </span>
          <div>
            <b>Пять решений. Новый сценарий.</b>
            <small>
              Карта показывает{" "}
              {after ? "город через два года" : "исходное состояние"}.
            </small>
          </div>
          <button
            className="icon-button"
            onClick={() => open("plan")}
            aria-label="Посмотреть результаты"
          >
            <ArrowUpRight size={19} />
          </button>
        </div>
      )}
      {panel === "plan" && (
        <PlanBuilder
          plan={plan}
          onChange={changePlan}
          selected={selected}
          onClose={close}
          onAsk={askPlan}
          onAdvisor={() => open("akim")}
        />
      )}
      {panel === "akim" && (
        <AkimPanel
          plan={plan}
          onChange={(p) => {
            changePlan(p);
            setToast("План применён. Карта и показатели обновлены.");
          }}
          onClose={close}
          onBuild={() => open("plan")}
        />
      )}
      {panel === "ask" && (
        <AskPanel
          plan={plan}
          poll={poll}
          onPoll={setPoll}
          onClose={close}
          initialQuestion={initialQuestion}
        />
      )}
      {panel === "data" && <CityDataPanel onClose={close} />}
      {panel === "about" && (
        <section
          className="about-panel glass"
          role="dialog"
          aria-labelledby="about-title"
        >
          <div className="panel-heading">
            <h2 id="about-title">Город, который можно изменить</h2>
            <button
              className="icon-button"
              onClick={close}
              aria-label="Закрыть справку"
            >
              <X size={20} />
            </button>
          </div>
          <p>
            Вы — аким на пять решений. Соберите план до {money(BUDGET_LIMIT)}{" "}
            млн ₸ и посмотрите, что изменится за 8 кварталов.
          </p>
          <div className="about-steps">
            <span>01 · Исследуйте районы</span>
            <ArrowDown size={15} />
            <span>02 · Выберите ровно пять мер</span>
            <ArrowDown size={15} />
            <span>03 · Спросите жителей и AI Акима</span>
          </div>
          <h3>Откуда берётся балл?</h3>
          <p>
            70% — средний балл районов с учётом населения, 30% — балл самого
            слабого района. За каждый показатель строго ниже 40 вычитается 1
            балл.
          </p>
          <code>0,7 × среднее + 0,3 × минимум − штраф</code>
          <p>
            Исходный балл: {fmt(baseline.score)}. Влияние мер учитывает задержку
            запуска и фиксированные синергии. Балл плана доступен только после
            пяти допустимых решений.
          </p>
          <div className="tradeoff">
            <b>Честная демосимуляция</b>
            <p>
              2 000 жителей имеют синтетические профили, дом, занятия и
              маршруты. Карта OpenStreetMap и геопортал показывают шесть реальных районов. Сценарные показатели рассчитаны для пяти. Погода, воздух, население и ДТП загружаются из
              открытых источников. Ответы GPT-6 Luna — прогнозы модели, а не
              реальный опрос. Можно явно переключиться на локальную демомодель.
            </p>
          </div>
          <p className="attribution">
            Поведение вдохновлено{" "}
            <a
              href="https://github.com/tejasprabhune/simfrancisco"
              target="_blank"
              rel="noreferrer"
            >
              Sim Francisco
            </a>
            . Спрайты:{" "}
            <a
              href="https://route1rodent.itch.io/16x16-rpg-character-sprite-sheet"
              target="_blank"
              rel="noreferrer"
            >
              Route1Rodent
            </a>
            ,{" "}
            <a
              href="https://creativecommons.org/licenses/by-sa/3.0/"
              target="_blank"
              rel="noreferrer"
            >
              CC BY-SA 3.0
            </a>
            , без изменений.
          </p>
          <button className="dark wide" onClick={() => open("plan")}>
            Создать свой план <ArrowUpRight size={16} />
          </button>
        </section>
      )}
      <nav className="dock glass" aria-label="Основные действия">
        <button
          className={`dock-plan ${panel === "plan" ? "active" : ""}`}
          onClick={() => (panel === "plan" ? close() : open("plan"))}
          aria-pressed={panel === "plan"}
        >
          <SlidersHorizontal size={17} />
          <span>{plan.length ? "Мой план" : "Создать план"}</span>
          <small>{plan.length}/5</small>
        </button>
        <span className="dock-divider" />
        <button
          className={panel === "ask" ? "active" : ""}
          onClick={() => {
            setInitialQuestion("");
            panel === "ask" ? close() : open("ask");
          }}
          aria-pressed={panel === "ask"}
        >
          <MessageCircle size={18} />
          <span>Спросить город</span>
        </button>
        <span className="dock-divider" />
        <button
          className={panel === "akim" ? "active" : ""}
          onClick={() => (panel === "akim" ? close() : open("akim"))}
          aria-pressed={panel === "akim"}
        >
          <Sparkles size={18} />
          <span>AI Аким</span>
          <i className="akim-dot" />
        </button>
      </nav>
      <div className="map-compass">
        <Compass size={26} strokeWidth={1} />
        <span>С</span>
      </div>
      <footer className="map-footer">
        <span>
          <i />
          Карта Астаны · жители и маршруты смоделированы
        </span>
        <button onClick={() => open("about")}>
          <HelpCircle size={13} />О симуляции
        </button>
      </footer>
      {toast && (
        <div className="toast glass" role="status">
          <Check size={16} />
          {toast}
        </div>
      )}
    </main>
  );
}
