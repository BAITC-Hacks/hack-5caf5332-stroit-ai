/* Connected workspace. All business values come from the local participant-pack API. */
const names = {
  audience: "Аудитория",
  pilots: "Пилоты",
  plan: "План кампаний",
};
const channels = {
  sms: "SMS",
  push: "Push",
  digital_ads: "Реклама",
  call: "Звонок",
};
const nf = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const pf = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});
const money = (n) => (n == null ? "Не оценено" : `${nf.format(n)} у.е.`);
const percent = (n) => (n == null ? "Нет оценки" : `${pf.format(n * 100)}%`);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const main = document.querySelector("#main");
const dialog = document.querySelector("#detail-dialog");
let params = new URLSearchParams(location.search);
let data = null,
  result = null,
  benchmark = null,
  busy = false,
  jobError = false,
  apiError = "",
  loading = true,
  ack = false,
  timer,
  trigger;
const screen = () =>
  Object.hasOwn(names, params.get("screen"))
    ? params.get("screen")
    : "audience";
const state = () =>
  ["loading", "empty", "error"].includes(params.get("state"))
    ? params.get("state")
    : "ready";
const announce = (text) => {
  document.querySelector("#announcer").textContent = text;
};
function url(values, replace = false) {
  for (const [key, value] of Object.entries(values))
    value ? params.set(key, value) : params.delete(key);
  history[replace ? "replaceState" : "pushState"]({}, "", `?${params}`);
  links();
}
function links() {
  document.querySelectorAll("a[data-screen]").forEach((a) => {
    const next = new URLSearchParams(params);
    next.set("screen", a.dataset.screen);
    next.delete("state");
    next.delete("detail");
    a.href = `?${next}`;
  });
}
async function api(path, options) {
  const response = await fetch(path, {
    ...options,
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
function heading(title, sub) {
  return `<div class="page-heading"><div><h1>${title}</h1><p>${sub}</p></div><button class="button button-primary" data-action="run" ${busy || loading || !data || state() !== "ready" ? "disabled" : ""}>${busy ? "Агент работает…" : result ? "Повторить подбор" : "Запустить подбор кампаний"}</button></div>`;
}
function blank(title, text, action = "retry", label = "Повторить загрузку") {
  return `<section class="panel empty-state"><h2 id="state-title">${title}</h2><p>${text}</p><button class="button button-primary" data-action="${action}">${label}</button></section>`;
}
function commonState() {
  if (state() === "error")
    return blank(
      "Тест состояния ошибки",
      "Это проверка интерфейса. Реальные результаты прогона не изменены.",
      "recover",
      "Вернуться к данным",
    );
  if (state() === "loading")
    return blank(
      "Загружаем данные…",
      "Тест отображения ожидания. Вычисления агента здесь не запускаются.",
      "recover",
      "Вернуться к данным",
    );
  if (state() === "empty")
    return blank(
      "Нет данных для отображения",
      "Тест пустого экрана. Сохранённые файлы не удалены.",
      "recover",
      "Вернуться к данным",
    );
  if (apiError)
    return blank(
      "Нет связи с локальным сервисом",
      "Проверьте, что запущен python3 server.py, затем обновите данные. Уже запущенный подбор мог продолжить работу.",
    );
  if (jobError)
    return blank(
      "Подбор не завершён",
      "Сервис сообщил об ошибке вычисления. Проверьте файлы engine и зависимости, затем повторите подбор.",
      "run",
      "Повторить подбор",
    );
  if (loading)
    return `<section class="panel empty-state" aria-busy="true"><h2 id="state-title">Загружаем данные кейса…</h2><p>Читаем агрегаты customer_profile.csv и статус сервиса.</p></section>`;
  if (busy)
    return `<section class="panel empty-state" aria-busy="true"><h2 id="state-title">Агент подбирает кампании…</h2><p>История → гипотезы → пилоты → план → внешний mock-evaluator. До 20 пилотов из общего бюджета. Это вычисление в локальной среде, не рассылка.</p><p>Можно переходить между экранами. Результат появится автоматически; лимит ожидания сервера — 5 минут.</p></section>`;
  return "";
}
function candidateName(c) {
  return `${c.current} · ${c.arpu}`;
}
function recommendations() {
  if (!result)
    return blank(
      "План ещё не построен",
      "Агент сам выберет гипотезы, проведёт пилоты и вернёт кампании. Данные уже загружены.",
      "run",
      "Запустить подбор кампаний",
    );
  const selected = result.audit.candidates.filter((c) => c.selected);
  return `<section class="panel recommendations"><div class="panel-header"><div><h2>Кампаний в плане: ${nf.format(selected.length)}</h2><p>Из завершённого прогона. Основания доступны для каждого варианта.</p></div><a class="button button-secondary" data-screen="plan" href="?screen=plan">Проверить план</a></div>${selected.map((c) => `<article class="recommendation-row"><div><h3>${esc(candidateName(c))}</h3><p><span translate="no">${esc(c.current)} → ${esc(c.target)}</span> · ${esc(channels[c.channel])}</p></div><span class="decision-status ${c.mean > c.se ? "has-evidence" : "needs-review"}">Пилотов: ${nf.format(c.pilot_count)} · ${percent(c.mean)}</span><button class="button button-secondary" data-detail="${esc(c.id)}" aria-label="Почему выбран ${esc(candidateName(c))}">Почему этот вариант</button></article>`).join("")}</section>`;
}
function audience() {
  return `${recommendations()}<dl class="metrics"><div class="metric"><dt>Абоненты в файле</dt><dd>${nf.format(data.rows)}</dd></div><div class="metric"><dt>Baseline, у.е.</dt><dd>${nf.format(data.baseline)}</dd></div><div class="metric"><dt>Исторические переходы</dt><dd>${nf.format(data.history_rows)}</dd></div><div class="metric"><dt>Ячейки тариф × ARPU</dt><dd>${nf.format(data.cells.length)}</dd></div></dl>
    <section class="panel" aria-labelledby="segments-title"><div class="panel-header"><div><h2 id="segments-title" tabindex="-1">Сегменты из файла</h2><p>Группировка по текущему тарифу и ARPU. Не готовые рекомендации.</p></div></div><form class="toolbar" role="search" id="filters"><label class="search-wrap"><span class="sr-only">Поиск тарифа</span><input name="q" id="segment-search" type="search" autocomplete="off" spellcheck="false" placeholder="Например, tariff_13…" value="${esc(params.get("q"))}"></label><div class="filter-wrap"><label for="arpu-filter">ARPU</label><select name="arpu" id="arpu-filter" autocomplete="off">${["all", "HIGH", "MID", "LOW"].map((v) => `<option value="${v}" ${v === (params.get("arpu") || "all") ? "selected" : ""}>${v === "all" ? "Все уровни" : v}</option>`).join("")}</select></div></form><div id="segment-results"></div></section>
    <section class="source-note"><h2>Откуда эти числа</h2><p>customer_profile.csv — аудитория; data/change_tariff.csv — история другой выборки; data/dict_tariff.csv — тарифы. Все файлы синтетические, выданы организатором. Это не данные клиентов Beeline.</p><p>Дубликаты ID: ${nf.format(data.quality.duplicate_ids)}. Пропущенные значения: ${nf.format(data.quality.missing_values)}. ${nf.format(data.rows - data.cells.reduce((n, c) => n + c.count, 0))} строк без полной ячейки тариф × ARPU исключены из планирования. Остальные обязательные поля проверяет агент.</p><p>SHA-256 профиля: <code>${esc(data.data_hashes["customer_profile.csv"].slice(0, 16))}…</code> Полные контрольные суммы — в audit JSON.</p></section>`;
}
function renderSegments() {
  const target = document.querySelector("#segment-results");
  if (!target) return;
  const q = (params.get("q") || "").trim().toLowerCase(),
    arpu = params.get("arpu") || "all";
  const rows = data.cells.filter(
    (c) =>
      (arpu === "all" || c.arpu === arpu) &&
      `${c.current} ${c.arpu}`.toLowerCase().includes(q),
  );
  const total = Math.max(1, Math.ceil(rows.length / 12)),
    page = Math.max(1, Math.min(total, parseInt(params.get("page"), 10) || 1));
  target.innerHTML = rows.length
    ? `<table class="data-table" role="table"><caption>Ячейки аудитории из customer_profile.csv</caption><thead role="rowgroup"><tr role="row"><th scope="col">Текущий тариф</th><th scope="col">ARPU</th><th scope="col">Абоненты</th><th scope="col">Средний baseline, у.е.</th></tr></thead><tbody role="rowgroup">${rows
        .slice((page - 1) * 12, page * 12)
        .map(
          (c) =>
            `<tr role="row"><td role="cell"><span class="segment-name" translate="no">${esc(c.current)}</span></td><td role="cell" data-label="ARPU">${esc(c.arpu)}</td><td role="cell" data-label="Абоненты">${nf.format(c.count)}</td><td role="cell" data-label="Средний baseline, у.е.">${nf.format(c.average)}</td></tr>`,
        )
        .join(
          "",
        )}</tbody></table><nav class="pagination" aria-label="Страницы сегментов"><button class="button button-secondary" data-page="${page - 1}" ${page === 1 ? "disabled" : ""}>Назад</button><span>${page} / ${total} · найдено ${nf.format(rows.length)}</span><button class="button button-secondary" data-page="${page + 1}" ${page === total ? "disabled" : ""}>Далее</button></nav>`
    : `<div class="empty-state"><h3>Таких сегментов нет</h3><p>Измените запрос или сбросьте фильтры.</p><button class="button button-secondary" data-action="clear">Сбросить фильтры</button></div>`;
  return rows.length;
}
const pilotReason = (p) =>
  p.reason.startsWith("Initial")
    ? "Первичная проверка гипотезы"
    : p.reason.startsWith("Repeat")
      ? "Уточнение перспективного варианта"
      : "Проверка альтернативы";
function pilots() {
  if (!result)
    return blank(
      "Пилотов пока нет",
      "Запустите подбор: агент проведёт исследование через env.run_pilot.",
      "run",
      "Запустить подбор кампаний",
    );
  const a = result.audit,
    r = a.remaining_after_pilots;
  return `<section class="run-context"><h2>Исследование завершено</h2><p>${nf.format(a.pilots.length)} пилотов. После исследования осталось ${money(r.budget)} и ${nf.format(r.contacts)} контактов. Из этого остатка финансируется финальный план.</p><p>Размер каждого повторного пилота и выбор следующей гипотезы зависели от полученных наблюдений.</p></section><section class="panel"><div class="panel-header"><div><h2>Журнал реального mock-прогона</h2><p>Наблюдения возвращены средой организатора, а не заданы интерфейсом.</p></div></div><ol class="pilot-list">${a.pilots.map((p, i) => `<li class="pilot-row"><span class="pilot-sequence" aria-label="Пилот ${i + 1}">${i + 1}</span><div class="pilot-description"><h3><span translate="no">${esc(p.filters.filter_current_tariff)} → ${esc(p.filters.target_tariff)}</span></h3><p>${esc(p.filters.filter_arpu_segment)} · ${esc(channels[p.filters.channel])}</p><span class="pilot-decision">${pilotReason(p)}</span><p>${nf.format(p.result.n_customers)} контактов · ${money(p.result.cost)}</p></div><div class="pilot-result"><strong class="${p.result.observed_lift_ratio < 0 ? "negative" : "positive"}">${percent(p.result.observed_lift_ratio)}</strong><button class="button button-text" data-detail="${esc(p.candidate)}" aria-label="Разбор пилота ${i + 1}">Разбор</button></div></li>`).join("")}</ol><p class="table-note">Шумный результат пилота — не истинный эффект. Повторы объединяются по фактическому размеру выборки; пересечения выборок неизвестны.</p></section>`;
}
function riskRequired() {
  return (
    result &&
    (result.audit.low_confidence_fallback ||
      result.audit.candidates.some((c) => c.selected && !(c.mean > c.se)))
  );
}
function plan() {
  if (!result)
    return blank(
      "План пока не построен",
      "Запустите агента, чтобы получить воспроизводимый submission.csv.",
      "run",
      "Запустить подбор кампаний",
    );
  const a = result.audit,
    e = result.evaluation,
    forecast = a.plan.every((p) => p.net != null)
      ? a.plan.reduce((n, p) => n + p.net, 0)
      : null;
  return `<div class="plan-summary"><section class="estimate"><span class="subtle-label">Оценка до evaluator</span><h2>Прогноз финальных кампаний</h2><strong class="estimate-value">${money(forecast)}</strong><p>По шумным пилотам, за вычетом финальных контактов. Эффект пилотов и их пересечения здесь не учтены.</p></section><section class="actual-result"><span class="subtle-label">После запуска · mock-среда</span><h2>Результат evaluator</h2><strong class="estimate-value ${e.net_arpu_gain < 0 ? "negative" : "positive"}">${money(e.net_arpu_gain)}</strong><p>Учитывает пилоты, все расходы и уникальных абонентов. Не прогноз для Beeline и не будущий балл судейства.</p></section></div>
    <dl class="metrics"><div class="metric"><dt>Все расходы</dt><dd>${money(e.total_cost)}</dd><dd class="metric-note">Лимит 100 000 у.е.</dd></div><div class="metric"><dt>Все контакты</dt><dd>${nf.format(e.total_contacts)}</dd><dd class="metric-note">Лимит 15 000</dd></div><div class="metric"><dt>Уникальные абоненты</dt><dd>${nf.format(e.unique_customers_targeted)}</dd></div><div class="metric"><dt>Финальные кампании</dt><dd>${nf.format(a.plan.length)} / 10</dd></div></dl>
    ${riskRequired() ? `<section class="risk-review"><h2>План требует осторожности</h2><p>Агент вернул вариант с недостаточной уверенностью. Положительный результат одного mock-прогона не снимает этот риск.</p><label><input id="ack-risk" name="ack-risk" type="checkbox" autocomplete="off" ${ack ? "checked" : ""}><span>Понимаю ограничения перед выгрузкой плана</span></label></section>` : ""}
    <section class="panel"><div class="panel-header"><div><h2>План, возвращённый агентом</h2><p>Порядок и фильтры сохранены без ручных изменений.</p></div><div class="flex-actions"><button class="button button-primary" data-export="csv" ${riskRequired() && !ack ? "disabled" : ""}>Скачать submission.csv</button><button class="button button-secondary" data-export="json" ${riskRequired() && !ack ? "disabled" : ""}>Скачать audit JSON</button></div></div>${a.plan
      .map((p) => {
        const c = a.candidates.find((c) => c.id === p.candidate);
        return `<article class="live-campaign"><div><h3>${esc(candidateName(c))}</h3><p class="campaign-route"><span translate="no">${esc(c.current)} → ${esc(c.target)}</span> · ${esc(channels[c.channel])}</p><button class="button button-text" data-detail="${esc(c.id)}" aria-label="Почему выбран ${esc(candidateName(c))}">Почему этот вариант</button></div><dl class="campaign-values"><div><dt>Контакты</dt><dd>${nf.format(p.contacts)}</dd></div><div><dt>Стоимость</dt><dd>${money(p.cost)}</dd></div><div><dt>Оценка net</dt><dd>${money(p.net)}</dd></div></dl></article>`;
      })
      .join(
        "",
      )}<p class="table-note">Выгрузка относится к этому прогону. Для сдачи тот же CSV воспроизводится командой python3 make_submission.py внутри engine.</p></section>
    ${benchmark?.agent ? `<section class="source-note"><h2>Проверка против стартового агента</h2><p>${nf.format(benchmark.runs.length)} одинаковых seed: медиана нового агента ${money(benchmark.agent.median)}, стартового — ${money(benchmark.starter.median)} Положительных результатов: ${benchmark.agent.positive}/${benchmark.runs.length}. Это сохранённый benchmark на mock, не результат текущего запуска.</p></section>` : ""}`;
}
function render() {
  const s = screen();
  document.title = `${names[s]} — Beeline Campaign Studio`;
  document.querySelector("#breadcrumb").textContent = names[s];
  document
    .querySelectorAll(".main-nav a")
    .forEach((a) =>
      a.dataset.screen === s
        ? a.setAttribute("aria-current", "page")
        : a.removeAttribute("aria-current"),
    );
  document.querySelector("#demo-state").value = state();
  const title = {
    audience: [
      "Подбор тарифных кампаний",
      "Данные кейса → адаптивные пилоты → проверяемый план.",
    ],
    pilots: [
      "Что узнал агент",
      "Гипотезы, затраты и наблюдения в порядке исследования.",
    ],
    plan: [
      "План и результат",
      "Прогноз агента отделён от оценки внешней mock-среды.",
    ],
  }[s];
  const status = commonState();
  main.innerHTML =
    heading(...title) +
    (status ||
      (s === "audience" ? audience() : s === "pilots" ? pilots() : plan()));
  if (data && !status && s === "audience") renderSegments();
  const stamp = document.querySelector("#run-stamp");
  stamp.textContent = result
    ? `Прогон ${result.run_id.slice(0, 8)} · seed ${result.seed} · ${new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Almaty" }).format(new Date(result.created_at * 1000))} (Алматы)`
    : "Локальный режим · данные организатора";
  links();
}
function detail(id, push = true) {
  const c = result?.audit.candidates.find((c) => c.id === id);
  if (!c) return;
  if (!dialog.open) trigger = document.activeElement;
  document.querySelector("#dialog-title").textContent = candidateName(c);
  const evidence = result.audit.pilots.filter((p) => p.candidate === id);
  document.querySelector("#dialog-content").innerHTML =
    `<p><span translate="no">${esc(c.current)} → ${esc(c.target)}</span> · ${esc(channels[c.channel])}</p><h3 class="decision-heading">Основание решения</h3><p>${c.selected ? "Выбран при последовательной сборке портфеля с учётом оценки эффекта, неопределённости и оставшихся ресурсов." : "Не вошёл в итоговый портфель: мог уступить альтернативе внутри ячейки, не пройти консервативный порог или не поместиться в ресурсы."}</p><dl class="detail-list"><div><dt>Среднее по пилотам</dt><dd>${percent(c.mean)}</dd></div><div><dt>Контакты пилотов</dt><dd>${nf.format(c.n)}</dd></div><div><dt>Приближённая ошибка SE</dt><dd>${percent(c.se)}</dd></div><div><dt>Исторические переходы</dt><dd>${nf.format(c.history_n)}</dd></div></dl><p class="notice">SE рассчитана с допущением о шуме из публичной среды и запасом 20%. Это не откалиброванная гарантия; неизвестное пересечение пилотов может завышать уверенность. История ранжирует гипотезы, но не задаёт конверсию.</p><h3 class="decision-heading">Наблюдения среды</h3><ul class="evidence-list">${evidence.map((p) => `<li><span>${esc(p.result.pilot)}</span><span>${percent(p.result.observed_lift_ratio)} · ${nf.format(p.result.n_customers)} контактов</span></li>`).join("") || "<li>Для fallback-варианта нет наблюдений.</li>"}</ul><h3 class="decision-heading">Альтернативы этой ячейки</h3><ul class="evidence-list">${
      result.audit.candidates
        .filter((x) => x.cell === c.cell && x.id !== c.id)
        .map(
          (x) =>
            `<li><span>${esc(x.target)} · ${esc(channels[x.channel])}</span><span>${x.n ? percent(x.mean) : "Не проверялся"}${x.selected ? " · выбран" : ""}</span></li>`,
        )
        .join("") || "<li>Альтернативы не исследованы.</li>"
    }</ul>`;
  dialog.classList.add("decision-drawer");
  if (push) url({ detail: id });
  if (!dialog.open) dialog.showModal();
  document.querySelector("#close-dialog").focus();
}
async function boot() {
  clearTimeout(timer);
  loading = true;
  apiError = "";
  render();
  try {
    const [d, s, b] = await Promise.all([
      api("/api/data"),
      api("/api/status"),
      api("/api/benchmark"),
    ]);
    data = d;
    benchmark = b;
    busy = s.status === "running";
    result = s.status === "complete" ? await api("/api/result") : null;
    jobError = s.status === "error";
    loading = false;
    render();
    if (busy) poll();
    else if (params.get("detail")) detail(params.get("detail"), false);
  } catch {
    loading = false;
    busy = false;
    apiError = "connection";
    render();
    announce("Не удалось загрузить сервис. Повторите загрузку.");
  }
}
async function run() {
  if (busy || loading || !data) return;
  busy = true;
  jobError = false;
  apiError = "";
  ack = false;
  url({ detail: null, state: null }, true);
  render();
  main.focus();
  announce("Агент начал подбор кампаний.");
  try {
    await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    poll();
  } catch {
    apiError = "start";
    busy = false;
    render();
    announce("Не удалось подтвердить запуск. Обновите статус сервиса.");
  }
}
function poll() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    try {
      const s = await api("/api/status");
      if (s.status === "running") {
        poll();
        return;
      }
      if (s.status !== "complete") {
        busy = false;
        jobError = true;
        render();
        announce("Подбор не завершён. Можно повторить запуск.");
        return;
      }
      result = await api("/api/result");
      busy = false;
      apiError = "";
      render();
      main.focus();
      announce(
        `Подбор завершён. Пилотов: ${result.audit.pilots.length}. Кампаний: ${result.audit.plan.length}.`,
      );
    } catch {
      busy = false;
      apiError = "poll";
      render();
      announce("Связь с подбором потеряна. Обновите статус.");
    }
  }, 700);
}
async function download(kind) {
  if (!result || busy || (riskRequired() && !ack)) return;
  try {
    const response = await fetch(
      `/api/${kind === "csv" ? "export.csv" : "audit.json"}?run_id=${encodeURIComponent(result.run_id)}`,
    );
    if (!response.ok) throw new Error();
    const blob = await response.blob();
    const address = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = address;
    a.download = kind === "csv" ? "submission.csv" : "audit.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(address), 1000);
    announce("Файл текущего прогона подготовлен.");
  } catch {
    announce("Не удалось скачать файл. Обновите данные и повторите.");
    document.querySelector("#download-error")?.remove();
    const p = document.createElement("p");
    p.id = "download-error";
    p.className = "validation-error";
    p.setAttribute("role", "alert");
    p.textContent =
      "Не удалось скачать файл. Обновите страницу и повторите загрузку.";
    main.prepend(p);
  }
}
document.addEventListener("click", (e) => {
  const nav = e.target.closest("a[data-screen]");
  if (
    nav &&
    !e.metaKey &&
    !e.ctrlKey &&
    !e.shiftKey &&
    !e.altKey &&
    e.button === 0
  ) {
    e.preventDefault();
    ack = false;
    url({ screen: nav.dataset.screen, detail: null, state: null });
    render();
    main.focus();
    return;
  }
  const info = e.target.closest("[data-detail]");
  if (info) {
    detail(info.dataset.detail);
    return;
  }
  const exp = e.target.closest("[data-export]");
  if (exp) {
    download(exp.dataset.export);
    return;
  }
  const page = e.target.closest("[data-page]");
  if (page) {
    url({ page: page.dataset.page });
    renderSegments();
    document.querySelector("#segments-title").focus();
    return;
  }
  const action = e.target.closest("[data-action]")?.dataset.action;
  if (action === "run") run();
  if (action === "retry") boot();
  if (action === "recover") {
    url({ state: null }, true);
    render();
    main.focus();
  }
  if (action === "clear") {
    url({ q: null, arpu: null, page: null }, true);
    render();
    document.querySelector("#segment-search").focus();
  }
});
document.addEventListener("submit", (e) => {
  if (e.target.id === "filters") e.preventDefault();
});
document.addEventListener("input", (e) => {
  if (e.target.id === "segment-search") {
    url({ q: e.target.value, page: null }, true);
    announce(`Найдено ячеек: ${renderSegments()}.`);
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "arpu-filter") {
    url(
      { arpu: e.target.value === "all" ? null : e.target.value, page: null },
      true,
    );
    announce(`Найдено ячеек: ${renderSegments()}.`);
  }
  if (e.target.id === "demo-state") {
    url({ state: e.target.value === "ready" ? null : e.target.value });
    render();
    announce("Состояние экрана изменено.");
  }
  if (e.target.id === "ack-risk") {
    ack = e.target.checked;
    document
      .querySelectorAll("[data-export]")
      .forEach((b) => (b.disabled = !ack));
    announce(
      ack ? "Экспорт доступен." : "Подтвердите ограничения перед экспортом.",
    );
  }
});
document
  .querySelector("#close-dialog")
  .addEventListener("click", () => dialog.close());
dialog.addEventListener("close", () => {
  if (params.has("detail")) url({ detail: null }, true);
  if (trigger?.isConnected) trigger.focus();
});
dialog.addEventListener("keydown", (e) => {
  if (e.key === "Tab") {
    const controls = [
      ...dialog.querySelectorAll("button,a[href],input,select"),
    ].filter((el) => !el.disabled);
    const first = controls[0],
      last = controls.at(-1);
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
});
addEventListener("popstate", () => {
  params = new URLSearchParams(location.search);
  ack = false;
  if (dialog.open && !params.has("detail")) dialog.close();
  render();
  if (params.has("detail")) detail(params.get("detail"), false);
});
boot();
