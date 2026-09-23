/* Standalone UI prototype. All campaign results below are illustrative fixtures, not evaluator output. */
(() => {
  "use strict";
  const names = {
    audience: "Аудитория",
    pilots: "Пилоты",
    plan: "План кампаний",
  };
  const nf = new Intl.NumberFormat("ru-RU");
  const pf = new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 1,
    signDisplay: "exceptZero",
  });
  const money = (value) => `${nf.format(value)} у.е.`;
  const escapeHTML = (value) =>
    String(value).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const icons = {
    arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
    alert: '<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 3v1"/>',
    download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    play: '<path d="m8 4 12 8-12 8V4Z"/>',
    up: '<path d="m5 15 7-7 7 7"/>',
    down: '<path d="m5 9 7 7 7-7"/>',
  };
  const icon = (name) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.arrow}</svg>`;
  const segments = [
    {
      id: "s1",
      title: "Активные пользователи",
      arpu: "HIGH",
      current: "tariff_4",
      count: 3400,
      avg: 9800,
      usage: "Много интернета",
      data: "HEAVY",
    },
    {
      id: "s2",
      title: "Ежедневная связь",
      arpu: "MID",
      current: "tariff_2",
      count: 4800,
      avg: 6200,
      usage: "Умеренный трафик",
      data: "LITE",
    },
    {
      id: "s3",
      title: "Интернет в приоритете",
      arpu: "HIGH",
      current: "tariff_6",
      count: 2700,
      avg: 11200,
      usage: "Много интернета",
      data: "HEAVY",
    },
    {
      id: "s4",
      title: "Базовые потребности",
      arpu: "LOW",
      current: "tariff_1",
      count: 4100,
      avg: 2900,
      usage: "Без интернета",
      data: "NON_USER",
    },
    {
      id: "s5",
      title: "Сбалансированный тариф",
      arpu: "MID",
      current: "tariff_5",
      count: 4600,
      avg: 5800,
      usage: "Умеренный трафик",
      data: "LITE",
    },
    {
      id: "s6",
      title: "Редкие контакты",
      arpu: "LOW",
      current: "tariff_3",
      count: 3841,
      avg: 2400,
      usage: "Без интернета",
      data: "NON_USER",
    },
  ];
  const pilotBase = [
    {
      id: "p1",
      segment: "s1",
      target: "tariff_10",
      channel: "sms",
      n: 80,
      ratio: 7.8,
      range: [1.2, 14.4],
      decision: "Уточнить размер эффекта",
    },
    {
      id: "p2",
      segment: "s2",
      target: "tariff_7",
      channel: "push",
      n: 120,
      ratio: 3.4,
      range: [-1.1, 7.9],
      decision: "Недостаточно уверенности",
    },
    {
      id: "p3",
      segment: "s3",
      target: "tariff_10",
      channel: "sms",
      n: 160,
      ratio: 6.1,
      range: [1.4, 10.8],
      decision: "Кандидат в план",
    },
    {
      id: "p4",
      segment: "s4",
      target: "tariff_5",
      channel: "push",
      n: 60,
      ratio: -2.6,
      range: [-8.8, 3.6],
      decision: "Не масштабировать",
    },
    {
      id: "p5",
      segment: "s5",
      target: "tariff_7",
      channel: "sms",
      n: 120,
      ratio: 4.3,
      range: [-0.9, 9.5],
      decision: "Сравнить с push",
    },
    {
      id: "p6",
      segment: "s1",
      target: "tariff_10",
      channel: "sms",
      n: 80,
      ratio: 8.2,
      range: [1.6, 14.8],
      decision: "Повтор подтверждает направление",
    },
  ];
  const channelCost = { push: 0, sms: 4, digital_ads: 22, call: 160 };
  const channelName = {
    push: "Push",
    sms: "SMS",
    digital_ads: "Digital ads",
    call: "Звонок",
  };
  const campaigns = [
    {
      id: "c1",
      segment: "s1",
      target: "tariff_10",
      channel: "sms",
      ratio: 8,
      confidence: "Два пилота",
      caution: false,
    },
    {
      id: "c2",
      segment: "s2",
      target: "tariff_7",
      channel: "push",
      ratio: 3.4,
      confidence: "Нужна повторная проверка",
      caution: true,
    },
    {
      id: "c3",
      segment: "s3",
      target: "tariff_10",
      channel: "sms",
      ratio: 6.1,
      confidence: "Один пилот",
      caution: false,
    },
    {
      id: "c4",
      segment: "s5",
      target: "tariff_7",
      channel: "sms",
      ratio: 4.3,
      confidence: "Нужна повторная проверка",
      caution: true,
    },
  ];
  let pilotRunning = false;
  let riskAcknowledged = false;
  const main = document.querySelector("#main");
  const dialog = document.querySelector("#detail-dialog");
  let params = new URLSearchParams(location.search);
  let screen = Object.hasOwn(names, params.get("screen"))
    ? params.get("screen")
    : "audience";
  let viewState = ["ready", "loading", "empty", "error"].includes(
    params.get("state"),
  )
    ? params.get("state")
    : "ready";
  let toastTimer;
  let operation = 0;
  let dialogTrigger;
  const sum = (items, fn) => items.reduce((total, item) => total + fn(item), 0);
  const extraPilots = () =>
    Math.max(0, Math.min(14, Number.parseInt(params.get("extra"), 10) || 0));
  const allPilots = () => [
    ...pilotBase,
    ...Array.from({ length: extraPilots() }, (_, i) => ({
      id: `p${i + 7}`,
      segment: "s1",
      target: "tariff_10",
      channel: "sms",
      n: 120,
      ratio: 7.1 + (i % 3) * 0.3,
      range: [2.5, 12.3],
      decision: "Демонстрационное уточнение",
    })),
  ];
  const pilotTotals = () => ({
    contacts: sum(allPilots(), (p) => p.n),
    cost: sum(allPilots(), (p) => p.n * channelCost[p.channel]),
  });
  function announce(message) {
    document.querySelector("#announcer").textContent = message;
  }
  function toast(message) {
    const el = document.querySelector("#toast");
    el.textContent = message;
    el.hidden = false;
    announce(message);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, 4500);
  }
  function updateURL(values, replace = false) {
    Object.entries(values).forEach(([key, value]) =>
      value ? params.set(key, value) : params.delete(key),
    );
    history[replace ? "replaceState" : "pushState"](
      {},
      "",
      `${location.pathname}?${params}${location.hash}`,
    );
    syncLinks();
  }
  function syncLinks() {
    document.querySelectorAll("a[data-screen]").forEach((link) => {
      const next = new URLSearchParams(params);
      next.set("screen", link.dataset.screen);
      next.delete("state");
      next.delete("detail");
      link.href = `?${next}`;
    });
  }
  function navigate(target) {
    operation++;
    riskAcknowledged = false;
    pilotRunning = false;
    screen = target;
    viewState = "ready";
    updateURL({ screen, state: null, detail: null });
    render();
    main.focus();
    announce(`Открыт экран «${names[screen]}».`);
  }
  function heading(title, subtitle, action = "") {
    return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div>${action}</div>`;
  }
  function stateContent() {
    if (viewState === "ready") return "";
    if (viewState === "loading")
      return `<section class="panel empty-state loading-block" aria-labelledby="state-title"><div class="loading-rail" aria-hidden="true"><span></span><span></span><span></span></div><h2 id="state-title">Загружаем ${screen === "audience" ? "аудиторию" : screen === "pilots" ? "пилоты" : "план"}…</h2><p>Демонстрация ожидания данных. Можно отменить загрузку и вернуться к примеру.</p><button class="button button-secondary" data-action="recover">Вернуться к демо</button></section>`;
    if (viewState === "error")
      return `<section class="panel empty-state" aria-labelledby="state-title"><span class="state-symbol error-symbol">${icon("alert")}</span><h2 id="state-title">Не удалось получить данные</h2><p>Это тестовое состояние ошибки. Повторите загрузку демонстрационного набора; ваши настройки сохранятся.</p><button class="button button-primary" data-action="retry">Повторить загрузку</button></section>`;
    return `<section class="panel empty-state" aria-labelledby="state-title"><span class="state-symbol">${icon("layers")}</span><h2 id="state-title">${screen === "audience" ? "Аудитория пока не загружена" : screen === "pilots" ? "Пилотов пока нет" : "План пока пуст"}</h2><p>${screen === "audience" ? "Откройте демонстрационный набор, чтобы увидеть сегменты и перейти к проверке гипотез." : screen === "pilots" ? "Откройте пример пилотов, чтобы сравнить каналы и оценить неопределённость." : "Откройте пример плана, чтобы выбрать кампании и проверить ограничения."}</p><button class="button button-primary" data-action="recover">Открыть демо-данные</button></section>`;
  }
  function audience() {
    const title = heading(
      "Выберите следующее решение",
      "Сначала основания для кампании. Затем — сегменты и ресурсы.",
      `<a class="button button-primary" href="?screen=pilots" data-screen="pilots">Перейти к пилотам ${icon("arrow")}</a>`,
    );
    if (viewState !== "ready") return title + stateContent();
    const groups = ["HIGH", "MID", "LOW"].map((key) => ({
      key,
      count: sum(
        segments.filter((s) => s.arpu === key),
        (s) => s.count,
      ),
    }));
    const total = sum(segments, (s) => s.count);
    return (
      title +
      recommendationOverview() +
      `<details class="audience-overview" data-disclosure="overview" ${params.get("overview") === "open" ? "open" : ""}><summary>Состав аудитории · ${nf.format(total)} абонент</summary><div class="audience-breakdown">${groups.map((g, i) => `<div><span>${["Высокий", "Средний", "Низкий"][i]} ARPU</span><strong>${nf.format(g.count)}</strong></div>`).join("")}</div><p>Общие лимиты: 100 000 у.е. · 15 000 контактов · 20 пилотов · до 10 кампаний. Не более 5 000 абонентов в одной кампании.</p></details><section class="panel" aria-labelledby="segments-title"><div class="panel-header"><div><h2 id="segments-title">Сегменты аудитории <span class="count-badge">${segments.length}</span></h2><p>Сначала тариф и ARPU, затем потребление</p></div></div><form class="toolbar" id="filters" role="search"><div class="search-wrap"><label for="segment-search" class="sr-only">Поиск сегмента или тарифа</label><span class="search-icon">${icon("search")}</span><input id="segment-search" name="q" type="search" autocomplete="off" spellcheck="false" placeholder="Например, tariff_4…" value="${escapeHTML(params.get("q") || "")}"></div><div class="filter-wrap"><label for="arpu-filter">ARPU</label><select id="arpu-filter" name="segment" autocomplete="off"><option value="all">Все уровни</option><option value="HIGH">Высокий</option><option value="MID">Средний</option><option value="LOW">Низкий</option></select></div><button class="button button-text" type="button" data-action="clear-filters">Сбросить</button></form><div id="segment-results"></div><p class="table-note">Числа иллюстративные. Сегменты не являются рекомендацией к запуску кампаний.</p></section>`
    );
  }
  function recommendationOverview() {
    const ready = campaigns.filter((c) => !c.caution);
    const review = campaigns.filter((c) => c.caution);
    const row = (c) => {
      const s = segments.find((s) => s.id === c.segment);
      return `<article class="recommendation-row"><div><h3>${s.title}</h3><p><span translate="no">${s.current} → ${c.target}</span> · <span translate="no">${channelName[c.channel]}</span></p></div><span class="decision-status ${c.caution ? "needs-review" : "has-evidence"}">${c.caution ? "Нужен ещё пилот" : c.confidence}</span><button class="button button-secondary" data-campaign-detail="${c.id}" aria-label="Почему: ${s.title}">Почему этот вариант</button></article>`;
    };
    return `<section class="panel recommendations" aria-labelledby="recommendations-title"><div class="panel-header"><div><h2 id="recommendations-title">Кандидаты в план</h2><p>Положительное направление в демо-пилотах. Не гарантия результата.</p></div><a class="button button-primary" href="?screen=plan" data-screen="plan">Проверить план</a></div>${ready.map(row).join("")}<details class="review-candidates" data-disclosure="review" ${params.get("review") === "open" ? "open" : ""}><summary>Ещё ${nf.format(review.length)} варианта требуют проверки</summary>${review.map(row).join("")}</details></section>`;
  }
  function openCampaign(id, push = true) {
    const c = campaigns.find((row) => row.id === id);
    if (!c) return;
    const s = segments.find((row) => row.id === c.segment);
    const evidence = allPilots().filter(
      (p) =>
        p.segment === c.segment &&
        p.target === c.target &&
        p.channel === c.channel,
    );
    dialogTrigger = document.activeElement;
    dialog.classList.add("decision-drawer");
    document.querySelector("#dialog-title").textContent = s.title;
    document.querySelector("#dialog-content").innerHTML = `
      <p class="decision-route"><span translate="no">${s.current} → ${c.target}</span> · <span translate="no">${channelName[c.channel]}</span></p>
      <span class="decision-status ${c.caution ? "needs-review" : "has-evidence"}">${c.caution ? "Требуется повторная проверка" : "Есть положительные демо-наблюдения"}</span>
      <h3 class="decision-heading">Почему этот вариант</h3>
      <p>${c.caution ? "Демо-диапазон включает ноль. Положительная точечная оценка недостаточна для уверенного масштабирования." : "В исходных пилотах направление эффекта положительное. Поэтому вариант включён в стартовый список, но требует проверки на реальных данных."}</p>
      <h3 class="decision-heading">На каких данных основан выбор</h3>
      <ul class="evidence-list">${evidence.map((p) => `<li><button class="button button-text" data-pilot-detail="${p.id}">Пилот ${p.id.slice(1)}</button><span>${nf.format(p.n)} контактов · ${pf.format(p.ratio)}%<small>Демо-диапазон: ${pf.format(p.range[0])}% … ${pf.format(p.range[1])}%</small></span></li>`).join("")}</ul>
      <p class="small muted">Диапазоны иллюстративные, не доверительные интервалы. Оценка кампании ${pf.format(c.ratio)}% задана в примере и не переобучается после демо-пилотов.</p>
      <h3 class="decision-heading">Почему не другой канал</h3>
      <p>Сравнительного пилота для этого сегмента нет. Нельзя утверждать, что ${channelName[c.channel]} лучше альтернатив. Следующий эксперимент должен сравнить варианты при сопоставимых условиях.</p>
      <dl class="detail-list"><div><dt>Контакты кампании</dt><dd>${nf.format(s.count)}</dd></div><div><dt>Стоимость контактов</dt><dd>${money(s.count * channelCost[c.channel])}</dd></div></dl>
      <p class="notice">${c.caution ? "Оставьте вне плана до проверки либо явно подтвердите риск при экспорте." : "Результаты синтетические. Перед реальным запуском нужны данные агента и итоговая оценка evaluator."}</p>`;
    if (push) updateURL({ detail: id });
    if (!dialog.open) dialog.showModal();
    document.querySelector("#close-dialog").focus();
  }
  function renderSegments() {
    const results = document.querySelector("#segment-results");
    if (!results) return;
    const query = (params.get("q") || "").trim().toLowerCase();
    const filter = params.get("segment") || "all";
    const rows = segments.filter(
      (s) =>
        (filter === "all" || s.arpu === filter) &&
        `${s.title} ${s.current} ${s.usage}`.toLowerCase().includes(query),
    );
    results.innerHTML = rows.length
      ? `<table class="data-table" role="table"><caption>Сегменты демонстрационной аудитории</caption><thead role="rowgroup"><tr role="row"><th scope="col">Сегмент / текущий тариф</th><th scope="col">ARPU</th><th scope="col" class="numeric">Абоненты</th><th scope="col" class="numeric">Средний ARPU, у.е.</th><th scope="col">Потребление</th><th scope="col"><span class="sr-only">Детали</span></th></tr></thead><tbody role="rowgroup">${rows.map((s) => `<tr role="row"><td role="cell"><div class="segment-name">${s.title}</div><div class="segment-meta" translate="no">${s.current}</div></td><td role="cell" data-label="Уровень ARPU"><span class="pill pill-${s.arpu.toLowerCase()}" translate="no">${s.arpu}</span></td><td role="cell" class="numeric" data-label="Абоненты">${nf.format(s.count)}</td><td role="cell" class="numeric" data-label="Средний ARPU, у.е.">${nf.format(s.avg)}</td><td role="cell" data-label="Потребление">${s.usage}</td><td role="cell"><button type="button" class="icon-button" data-detail="${s.id}" aria-label="Подробнее: ${s.title}">${icon("arrow")}</button></td></tr>`).join("")}</tbody></table>`
      : `<div class="empty-state"><span class="state-symbol">${icon("search")}</span><h3>Таких сегментов нет</h3><p>Измените запрос или сбросьте фильтр ARPU.</p><button class="button button-secondary" data-action="clear-filters">Сбросить фильтры</button></div>`;
    return rows.length;
  }
  function pilots() {
    const title = heading(
      "Проверка гипотез",
      "Следующий эксперимент, его стоимость и все предыдущие наблюдения.",
      `<a class="button button-primary" href="?screen=plan" data-screen="plan">Собрать план ${icon("arrow")}</a>`,
    );
    if (viewState !== "ready") return title + stateContent();
    const totals = pilotTotals();
    const count = allPilots().length;
    return (
      title +
      `<div class="pilot-workflow"><aside class="research-side"><section class="next-step pilot-next" aria-labelledby="hypothesis-title"><span class="step-label">Следующий демо-эксперимент</span><h2 id="hypothesis-title">Уточнить эффект SMS</h2><p>Ещё 120 контактов для активных пользователей. Проверяем, сохраняется ли положительное направление при повторе.</p><div class="hypothesis-cost"><span>Стоимость демо-пилота</span><strong>${money(480)}</strong></div><button class="button button-dark" id="run-pilot" data-action="run-pilot" ${count >= 20 ? "disabled" : ""}>${icon("play")} ${count >= 20 ? "Лимит пилотов достигнут" : "Запустить демо-пилот"}</button><p class="small">Размер 120 задан в демо, не рассчитан агентом. Реальная рассылка не запускается.</p><div id="pilot-progress" hidden><p role="status">Проверяем гипотезу…</p><button class="button button-text" data-action="cancel-pilot">Отменить пилот</button></div></section><section class="research-budget" aria-labelledby="resources-title"><h2 id="resources-title">После текущих пилотов</h2><div class="resource"><div><span>Пилоты</span><strong>${nf.format(count)} <span class="muted">/ 20</span></strong></div><progress max="20" value="${count}" aria-label="Использовано пилотов: ${count} из 20"></progress></div><div class="resource"><div><span>Осталось бюджета</span><strong>${money(100000 - totals.cost)}</strong></div><p>Пилоты: ${money(totals.cost)} Финальный план ещё не вычтен.</p></div><div class="resource"><div><span>Осталось контактов</span><strong>${nf.format(15000 - totals.contacts)}</strong></div><p>Пилоты: ${nf.format(totals.contacts)}. Остаток общий с планом.</p></div></section></aside><section class="panel pilot-main" aria-labelledby="pilot-title"><div class="panel-header"><div><h2 id="pilot-title">Журнал исследования <span class="count-badge">${nf.format(count)}</span></h2><p>Наблюдаемый эффект, не гарантированный результат</p></div><span class="pill">Демо-прогон</span></div><div class="toolbar"><div class="filter-wrap"><label for="channel-filter">Канал</label><select id="channel-filter" name="channel" autocomplete="off"><option value="all">Все каналы</option><option value="sms">SMS</option><option value="push">Push</option><option value="call">Звонок</option><option value="digital_ads">Digital ads</option></select></div></div><div id="pilot-results"></div><p class="table-note">Диапазоны иллюстративные, не калиброванные доверительные интервалы. Отрицательные наблюдения сохранены.</p></section></div>`
    );
  }
  function renderPilots() {
    const target = document.querySelector("#pilot-results");
    if (!target) return;
    const channel = params.get("channel") || "all";
    const rows = allPilots().filter(
      (p) => channel === "all" || p.channel === channel,
    );
    target.innerHTML = rows.length
      ? `<ol class="pilot-list">${rows
          .map((p) => {
            const s = segments.find((s) => s.id === p.segment);
            return `<li class="pilot-row"><div class="pilot-sequence" aria-label="Пилот ${p.id.slice(1)}">${p.id.slice(1)}</div><div class="pilot-description"><h3>${s.title}</h3><p><span translate="no">${s.current}</span> <span aria-label="на">→</span> <span translate="no">${p.target}</span><span class="pilot-channel" translate="no">${channelName[p.channel]}</span></p><span class="pilot-decision ${p.ratio < 0 ? "negative" : ""}">${p.decision}</span></div><div class="pilot-result"><strong class="${p.ratio < 0 ? "negative" : "positive"}">${pf.format(p.ratio)}%</strong><span>${nf.format(p.n)} контактов</span><button class="button button-text" data-pilot-detail="${p.id}" aria-label="Разбор пилота ${p.id.slice(1)}: ${s.title}">Разбор</button></div></li>`;
          })
          .join("")}</ol>`
      : `<div class="empty-state"><span class="state-symbol">${icon("layers")}</span><h3>Пилотов в этом канале нет</h3><p>Выберите другой канал или покажите все результаты исследования.</p><button class="button button-secondary" data-action="all-channels">Показать все каналы</button></div>`;
    return rows.length;
  }
  function openPilot(id, push = true) {
    const p = allPilots().find((p) => p.id === id);
    if (!p) return;
    if (!dialog.open) dialogTrigger = document.activeElement;
    dialog.classList.remove("decision-drawer");
    const s = segments.find((s) => s.id === p.segment);
    document.querySelector("#dialog-title").textContent =
      `Пилот ${id.slice(1)}: ${channelName[p.channel]}`;
    document.querySelector("#dialog-content").innerHTML =
      `<p>${s.title}</p><dl class="detail-list"><div><dt>Наблюдаемый эффект</dt><dd class="${p.ratio < 0 ? "negative" : "positive"}">${pf.format(p.ratio)}%</dd></div><div><dt>Фактический размер</dt><dd>${nf.format(p.n)} абонентов</dd></div><div><dt>Стоимость контактов</dt><dd>${money(p.n * channelCost[p.channel])}</dd></div><div><dt>Пример диапазона</dt><dd>${pf.format(p.range[0])}% … ${pf.format(p.range[1])}%</dd></div></dl><h3>Что это меняет</h3><p class="dialog-explanation">${p.decision}. ${p.range[0] <= 0 ? "Диапазон включает ноль: положительный эффект пока не подтверждён." : "В примере направление положительное. Перед масштабированием нужно проверить устойчивость на данных агента."}</p><p class="notice">Демо-наблюдение уже включает влияние канала. Диапазон задан для иллюстрации UI; это не результат статистической оценки реальной аудитории.</p>`;
    if (push) updateURL({ detail: id });
    if (!dialog.open) dialog.showModal();
    document.querySelector("#close-dialog").focus();
  }
  async function runPilot() {
    if (pilotRunning || allPilots().length >= 20) return;
    pilotRunning = true;
    const token = ++operation;
    const button = document.querySelector("#run-pilot");
    button.setAttribute("aria-disabled", "true");
    button.textContent = "Проверяем гипотезу…";
    document.querySelector("#pilot-progress").hidden = false;
    announce("Запущен демонстрационный пилот. Ожидайте результат.");
    await new Promise((resolve) => setTimeout(resolve, 1300));
    if (token !== operation) return;
    pilotRunning = false;
    updateURL({ extra: String(extraPilots() + 1), channel: null });
    render();
    const runButton = document.querySelector("#run-pilot");
    (runButton && !runButton.disabled ? runButton : main).focus();
    toast("Демо-пилот завершён. Журнал и остатки ресурсов обновлены.");
  }
  function selectedCampaigns() {
    const ids = params.has("selected")
      ? params.get("selected").split(",")
      : ["c1", "c3"];
    return orderedCampaigns().filter((c) => ids.includes(c.id));
  }
  function orderedCampaigns() {
    const ids = [...new Set((params.get("order") || "").split(","))].filter(
      (id) => campaigns.some((c) => c.id === id),
    );
    return [
      ...ids.map((id) => campaigns.find((c) => c.id === id)),
      ...campaigns
        .filter((c) => !ids.includes(c.id))
        .sort((a, b) => Number(a.caution) - Number(b.caution)),
    ];
  }
  function planTotals() {
    const selected = selectedCampaigns();
    const pilots = pilotTotals();
    const contactCount = sum(
      selected,
      (c) => segments.find((s) => s.id === c.segment).count,
    );
    const cost = sum(
      selected,
      (c) =>
        segments.find((s) => s.id === c.segment).count * channelCost[c.channel],
    );
    const gross = Math.round(
      sum(selected, (c) => {
        const s = segments.find((s) => s.id === c.segment);
        return (s.count * s.avg * c.ratio) / 100;
      }),
    );
    return {
      selected,
      contacts: contactCount,
      cost,
      gross,
      net: gross - cost,
      pilotCost: pilots.cost,
      pilotContacts: pilots.contacts,
      valid:
        selected.length > 0 &&
        selected.length <= 10 &&
        contactCount + pilots.contacts <= 15000 &&
        cost + pilots.cost <= 100000,
    };
  }
  function plan() {
    const title = heading(
      "План кампаний",
      "Проверьте основания, расходы и риски перед экспортом.",
      `<button class="button button-primary" id="export-csv" data-action="export-csv">${icon("download")} Скачать демо CSV</button>`,
    );
    if (viewState !== "ready")
      return (
        title.replace('id="export-csv"', 'disabled id="export-csv"') +
        stateContent()
      );
    return (
      title +
      `<div id="plan-summary"></div><section class="panel" aria-labelledby="campaigns-title"><div class="panel-header"><div><h2 id="campaigns-title">Состав плана</h2><p>Применяются сверху вниз. Измените порядок кнопками со стрелками.</p></div><button class="button button-text" data-action="export-audit">Скачать JSON</button></div><div id="campaign-list"></div><p class="table-note">Выбор и порядок сохраняются в URL. Демо-сегменты не пересекаются между собой; пересечение с пилотами неизвестно.</p></section><div class="plan-footnotes"><div>${icon("check")}<p><strong>Пилоты учтены в расходах</strong><br>Повторные контакты расходуют общий лимит, даже если канал бесплатный.</p></div><div>${icon("alert")}<p><strong>Это оценка, а не выручка</strong><br>Итоговый net по уникальным клиентам может посчитать только evaluator.</p></div></div>`
    );
  }
  function renderPlan() {
    const summary = document.querySelector("#plan-summary");
    if (!summary) return;
    const t = planTotals();
    const allContacts = t.contacts + t.pilotContacts;
    const allCost = t.cost + t.pilotCost;
    const overContacts = allContacts > 15000;
    const overCost = allCost > 100000;
    const risky = t.selected.filter((c) => c.caution);
    const canExport = t.valid && (!risky.length || riskAcknowledged);
    document.querySelector("#export-csv").disabled = !canExport;
    document.querySelector('[data-action="export-audit"]').disabled =
      !canExport;
    summary.innerHTML = `<section class="plan-summary" aria-labelledby="estimate-title"><div class="estimate"><span class="subtle-label">Демо-прогноз · не фактическая выручка</span><h2 id="estimate-title">Эффект финальных кампаний</h2><strong class="estimate-value">${t.net > 0 ? "+" : ""}${nf.format(t.net)} <small>у.е.</small></strong><dl class="calculation"><div><dt>Эффект до расходов</dt><dd>${money(t.gross)}</dd></div><div><dt>Финальные контакты</dt><dd>−${money(t.cost)}</dd></div><div><dt>Расходы на пилоты, отдельно</dt><dd>${money(t.pilotCost)}</dd></div></dl><p>Эффект пилотов и пересечения неизвестны. Итоговый net всего прогона и его неопределённость не оценены.</p></div><div class="plan-resources"><div class="resource"><div><span>Бюджет с пилотами</span><strong class="${overCost ? "negative" : ""}">${money(allCost)} <span class="muted">/ ${nf.format(100000)}</span></strong></div><progress max="100000" value="${Math.min(allCost, 100000)}" aria-label="Бюджет: ${allCost} из 100000 у.е."></progress><p>Пилоты ${money(t.pilotCost)} + план ${money(t.cost)}</p></div><div class="resource"><div><span>Контакты с пилотами</span><strong class="${overContacts ? "negative" : ""}">${nf.format(allContacts)} <span class="muted">/ ${nf.format(15000)}</span></strong></div><progress max="15000" value="${Math.min(allContacts, 15000)}" aria-label="Контакты: ${allContacts} из 15000"></progress><p>Пилоты ${nf.format(t.pilotContacts)} + план ${nf.format(t.contacts)}</p></div><div class="plan-check ${t.valid && !risky.length ? "positive" : "negative"}">${icon(t.valid && !risky.length ? "check" : "alert")}<span>${t.valid ? `Лимиты соблюдены. Кампаний: ${nf.format(t.selected.length)} из 10.${risky.length ? " Есть непроверенные варианты." : ""}` : t.selected.length === 0 ? "Выберите хотя бы одну кампанию для экспорта." : "Лимит превышен. Исключите кампанию из плана."}</span></div></div></section>${t.selected.length === 0 ? `<div class="plan-empty"><h3>Ни одна кампания не выбрана</h3><p>Отметьте кампанию ниже или восстановите пример.</p><button class="button button-secondary" data-action="restore-plan">Выбрать 2 кандидата в план</button></div>` : ""}${overContacts || overCost ? `<p class="validation-error" role="alert">${overContacts ? `Превышение контактов: ${nf.format(allContacts - 15000)}. ` : ""}${overCost ? `Превышение бюджета: ${money(allCost - 100000)}. ` : ""}Снимите выбор с одной из кампаний. Экспорт недоступен до исправления.</p>` : ""}`;
    summary.innerHTML += risky.length
      ? `<section class="risk-review" aria-labelledby="risk-title"><h3 id="risk-title">В плане есть непроверенные кампании</h3><p>${risky.map((c) => segments.find((s) => s.id === c.segment).title).join(", ")}. В этих наблюдениях демо-диапазон включает ноль. Снимите выбор либо подтвердите риск, чтобы открыть экспорт.</p><label for="ack-risk"><input type="checkbox" id="ack-risk" name="ack-risk" autocomplete="off" ${riskAcknowledged ? "checked" : ""}><span>Понимаю, что положительный эффект этих кампаний не подтверждён</span></label></section>`
      : "";
    document.querySelector("#campaign-list").innerHTML = orderedCampaigns()
      .map((c, index) => {
        const s = segments.find((s) => s.id === c.segment);
        const selected = t.selected.some((row) => row.id === c.id);
        const net = Math.round(
          (s.count * s.avg * c.ratio) / 100 - s.count * channelCost[c.channel],
        );
        return `<article class="campaign-row ${selected ? "is-selected" : ""}" data-campaign="${c.id}"><div class="campaign-main"><label class="campaign-label" for="select-${c.id}"><input type="checkbox" id="select-${c.id}" aria-describedby="evidence-${c.id}" name="campaign" value="${c.id}" autocomplete="off" ${selected ? "checked" : ""}><span><strong>${s.title}</strong><span class="campaign-route"><span translate="no">${s.current}</span> → <span translate="no">${c.target}</span><span class="pill" translate="no">${channelName[c.channel]}</span></span></span></label><span id="evidence-${c.id}" class="confidence decision-status ${c.caution ? "needs-review" : "has-evidence"}">${c.confidence}</span><button class="button button-text campaign-why" data-campaign-detail="${c.id}" aria-label="Почему: ${s.title}">Почему этот вариант</button></div><dl class="campaign-values"><div><dt>Контакты</dt><dd>${nf.format(s.count)}</dd></div><div><dt>Стоимость</dt><dd>${money(s.count * channelCost[c.channel])}</dd></div><div><dt>Оценка net</dt><dd class="positive">+${nf.format(net)}</dd></div></dl><div class="reorder" role="group" aria-label="Порядок кампании ${escapeHTML(s.title)}"><button class="icon-button" data-move="up" data-id="${c.id}" aria-label="Поднять: ${s.title}" ${index === 0 ? "disabled" : ""}>${icon("up")}</button><button class="icon-button" data-move="down" data-id="${c.id}" aria-label="Опустить: ${s.title}" ${index === campaigns.length - 1 ? "disabled" : ""}>${icon("down")}</button></div></article>`;
      })
      .join("");
  }
  function exportPlan(kind) {
    const totals = planTotals();
    if (
      !totals.valid ||
      (totals.selected.some((c) => c.caution) && !riskAcknowledged) ||
      viewState !== "ready"
    ) {
      toast("Проверьте выбор кампаний и лимиты перед экспортом.");
      return;
    }
    const output = totals.selected.map((c) => {
      const s = segments.find((s) => s.id === c.segment);
      return {
        campaign_name: `demo_${c.id}_${c.channel}`,
        filter_arpu_segment: s.arpu,
        filter_data_segment: null,
        filter_call_segment: null,
        filter_current_tariff: s.current,
        target_tariff: c.target,
        channel: c.channel,
      };
    });
    const fields = [
      "campaign_name",
      "filter_arpu_segment",
      "filter_data_segment",
      "filter_call_segment",
      "filter_current_tariff",
      "target_tariff",
      "channel",
    ];
    const data =
      kind === "csv"
        ? [
            fields.join(","),
            ...output.map((row) =>
              fields.map((key) => row[key] ?? "").join(","),
            ),
          ].join("\r\n") + "\r\n"
        : JSON.stringify(
            {
              demo: true,
              risk_acknowledged: riskAcknowledged,
              generated_at: new Date().toISOString(),
              limitations:
                "Illustrative fixtures; not evaluator output. Net is final-campaign estimate only. Pilot overlap unknown.",
              campaigns: output,
              totals,
              pilots: allPilots(),
            },
            null,
            2,
          );
    const url = URL.createObjectURL(
      new Blob([data], {
        type:
          kind === "csv"
            ? "text/csv;charset=utf-8"
            : "application/json;charset=utf-8",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = kind === "csv" ? "demo-submission.csv" : "demo-audit.json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast(
      `Экспорт ${kind.toUpperCase()} подготовлен. Это демонстрационный файл, не готовая заявка организатору.`,
    );
  }
  function openDetail(id, push = true) {
    const s = segments.find((row) => row.id === id);
    if (!s) return;
    dialogTrigger = document.activeElement;
    dialog.classList.remove("decision-drawer");
    document.querySelector("#dialog-title").textContent = s.title;
    document.querySelector("#dialog-content").innerHTML =
      `<p class="muted">Сегмент демонстрационной аудитории</p><dl class="detail-list"><div><dt>Текущий тариф</dt><dd translate="no">${s.current}</dd></div><div><dt>Уровень ARPU</dt><dd translate="no">${s.arpu}</dd></div><div><dt>Абоненты</dt><dd>${nf.format(s.count)}</dd></div><div><dt>Средний ARPU</dt><dd>${money(s.avg)}</dd></div></dl><p class="notice">До выбора нового тарифа проверьте гипотезу пилотом. Высокий ARPU сам по себе не означает положительный эффект.</p>`;
    if (push) updateURL({ detail: id });
    if (!dialog.open) dialog.showModal();
  }
  function render() {
    document.title = `${names[screen]} — Beeline Campaign Studio`;
    document.querySelector("#breadcrumb").textContent = names[screen];
    document
      .querySelectorAll(".main-nav a")
      .forEach((a) =>
        a.dataset.screen === screen
          ? a.setAttribute("aria-current", "page")
          : a.removeAttribute("aria-current"),
      );
    document.querySelector("#demo-state").value = viewState;
    main.innerHTML =
      screen === "audience"
        ? audience()
        : screen === "pilots"
          ? pilots()
          : plan();
    if (screen === "audience" && viewState === "ready") {
      const value = params.get("segment");
      document.querySelector("#arpu-filter").value = [
        "HIGH",
        "MID",
        "LOW",
      ].includes(value)
        ? value
        : "all";
      renderSegments();
    }
    if (screen === "pilots" && viewState === "ready") {
      document.querySelector("#channel-filter").value =
        params.get("channel") || "all";
      renderPilots();
    }
    if (screen === "plan" && viewState === "ready") renderPlan();
    syncLinks();
  }
  async function recover(withDelay) {
    const token = ++operation;
    if (withDelay) {
      viewState = "loading";
      updateURL({ state: "loading" }, true);
      render();
      main.focus();
      announce("Загружаем демо-данные…");
      await new Promise((resolve) => setTimeout(resolve, 850));
    }
    if (token !== operation) return;
    viewState = "ready";
    updateURL({ state: null }, true);
    render();
    main.focus();
    announce("Демо-данные загружены.");
  }
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-screen]");
    if (
      link &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.shiftKey &&
      !event.altKey &&
      event.button === 0
    ) {
      event.preventDefault();
      navigate(link.dataset.screen);
      return;
    }
    const campaignDetail = event.target.closest("[data-campaign-detail]");
    if (campaignDetail) {
      openCampaign(campaignDetail.dataset.campaignDetail);
      return;
    }
    const detail = event.target.closest("[data-detail]");
    if (detail) {
      openDetail(detail.dataset.detail);
      return;
    }
    const pilotDetail = event.target.closest("[data-pilot-detail]");
    if (pilotDetail) {
      openPilot(pilotDetail.dataset.pilotDetail);
      return;
    }
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (action === "export-csv") exportPlan("csv");
    if (action === "export-audit") exportPlan("json");
    if (action === "restore-plan") {
      riskAcknowledged = false;
      updateURL({ selected: "c1,c3" });
      renderPlan();
      document.querySelector("#select-c1").focus();
      announce(
        "Выбраны 2 демонстрационные кампании без пометки повторной проверки.",
      );
    }
    const move = event.target.closest("[data-move]");
    if (move) {
      const list = orderedCampaigns().map((c) => c.id);
      const index = list.indexOf(move.dataset.id);
      const next = index + (move.dataset.move === "up" ? -1 : 1);
      if (next >= 0 && next < list.length) {
        [list[index], list[next]] = [list[next], list[index]];
        updateURL({ order: list.join(",") });
        renderPlan();
        const nextButton = document.querySelector(
          `[data-id="${move.dataset.id}"][data-move="${move.dataset.move}"]`,
        );
        (nextButton.disabled
          ? document.querySelector(`#select-${move.dataset.id}`)
          : nextButton
        ).focus();
        announce(`Кампания перемещена на позицию ${next + 1}.`);
      }
    }
    if (action === "run-pilot") runPilot();
    if (action === "cancel-pilot") {
      operation++;
      pilotRunning = false;
      render();
      document.querySelector("#run-pilot").focus();
      toast("Демо-пилот отменён. Ресурсы не потрачены.");
    }
    if (action === "all-channels") {
      updateURL({ channel: null }, true);
      document.querySelector("#channel-filter").value = "all";
      renderPilots();
      document.querySelector("#channel-filter").focus();
      announce("Показаны все каналы.");
    }
    if (action === "recover" || action === "retry") recover(action === "retry");
    if (action === "clear-filters") {
      updateURL({ q: null, segment: null }, true);
      document.querySelector("#segment-search").value = "";
      document.querySelector("#arpu-filter").value = "all";
      renderSegments();
      document.querySelector("#segment-search").focus();
      announce("Фильтры сброшены. Показаны все сегменты.");
    }
  });
  document.addEventListener(
    "toggle",
    (event) => {
      const key = event.target.dataset?.disclosure;
      if (key && event.target.isConnected) {
        updateURL({ [key]: event.target.open ? "open" : null }, true);
      }
    },
    true,
  );
  document.addEventListener("submit", (event) => {
    if (event.target.id === "filters") event.preventDefault();
  });
  document.addEventListener("input", (event) => {
    if (event.target.id === "segment-search") {
      updateURL({ q: event.target.value || null }, true);
      const count = renderSegments();
      announce(`Найдено сегментов: ${count}.`);
    }
  });
  document.addEventListener("change", (event) => {
    if (event.target.name === "campaign") {
      riskAcknowledged = false;
      const id = event.target.value;
      const selected = new Set(selectedCampaigns().map((c) => c.id));
      event.target.checked ? selected.add(id) : selected.delete(id);
      updateURL({ selected: [...selected].join(",") || "none" });
      renderPlan();
      document.querySelector(`#select-${id}`).focus();
      const t = planTotals();
      announce(
        `Кампаний выбрано: ${t.selected.length}. ${t.selected.some((c) => c.caution) ? "Есть непроверенные кампании. Подтвердите риск или снимите их выбор; экспорт недоступен." : t.valid ? "Лимиты соблюдены." : "Проверьте выбор и лимиты. Экспорт недоступен."}`,
      );
    }
    if (event.target.id === "ack-risk") {
      riskAcknowledged = event.target.checked;
      renderPlan();
      document.querySelector("#ack-risk").focus();
      announce(
        riskAcknowledged
          ? "Риск подтверждён. Экспорт доступен при соблюдении лимитов."
          : "Риск не подтверждён. Экспорт недоступен.",
      );
    }
    if (event.target.id === "channel-filter") {
      updateURL(
        { channel: event.target.value === "all" ? null : event.target.value },
        true,
      );
      const count = renderPilots();
      announce(`Найдено пилотов: ${count}.`);
    }
    if (event.target.id === "arpu-filter") {
      updateURL(
        { segment: event.target.value === "all" ? null : event.target.value },
        true,
      );
      const count = renderSegments();
      announce(`Найдено сегментов: ${count}.`);
    }
    if (event.target.id === "demo-state") {
      operation++;
      pilotRunning = false;
      viewState = event.target.value;
      updateURL({ state: viewState === "ready" ? null : viewState });
      render();
      announce(`Состояние: ${event.target.selectedOptions[0].textContent}.`);
    }
  });
  // Keep native pointer/select UI; make arrow selection deterministic on desktop browsers.
  document.addEventListener(
    "keydown",
    (event) => {
      const select = event.target;
      if (
        !(select instanceof HTMLSelectElement) ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey
      )
        return;
      const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      const last = select.options.length - 1;
      const next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? last
            : Math.max(
                0,
                Math.min(
                  last,
                  select.selectedIndex + (event.key === "ArrowDown" ? 1 : -1),
                ),
              );
      if (next !== select.selectedIndex) {
        select.selectedIndex = next;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    },
    true,
  );
  document
    .querySelector("#close-dialog")
    .addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    if (!dialog.open && params.has("detail")) updateURL({ detail: null }, true);
    if (!dialog.open && dialogTrigger?.isConnected) dialogTrigger.focus();
  });
  dialog.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const targets = Array.from(
      dialog.querySelectorAll(
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => el.getClientRects().length > 0);
    const first = targets[0];
    const last = targets[targets.length - 1];
    if (!first) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  window.addEventListener("popstate", () => {
    operation++;
    riskAcknowledged = false;
    pilotRunning = false;
    params = new URLSearchParams(location.search);
    screen = Object.hasOwn(names, params.get("screen"))
      ? params.get("screen")
      : "audience";
    viewState = ["loading", "empty", "error"].includes(params.get("state"))
      ? params.get("state")
      : "ready";
    const detailId = params.get("detail");
    if (dialog.open && !detailId) dialog.close();
    render();
    if (detailId)
      detailId.startsWith("p")
        ? openPilot(detailId, false)
        : detailId.startsWith("c")
          ? openCampaign(detailId, false)
          : openDetail(detailId, false);
  });
  render();
  if (params.has("detail"))
    params.get("detail").startsWith("p")
      ? openPilot(params.get("detail"), false)
      : params.get("detail").startsWith("c")
        ? openCampaign(params.get("detail"), false)
        : openDetail(params.get("detail"), false);
})();
