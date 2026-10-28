(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const PHENOMENA = {
    "temperature|below": "a cold spot", "temperature|above": "a warmth with no source",
    "humidity|above": "breath on the glass", "humidity|below": "the air drying out",
    "energy|above": "the machines waking up", "energy|below": "the house going too quiet",
    "light|above": "lights coming on", "light|below": "lights going out",
  };
  const CREW = {
    medium: { name: "Luna", role: "the Medium", img: "/static/characters/luna.svg",
      bio: "A tiny sugar-skull ghost with a marigold crown. She floats through the house at night and feels every presence in her crystal ball.",
      line: "Shhh... the house is breathing." },
    skeptic: { name: "Dr. Bigotes", role: "the Skeptic", img: "/static/characters/bigotes.svg",
      bio: "A black cat scientist with round glasses and a flashlight. He has never met a ghost that was not a kettle, a draft or a thermostat.",
      line: "Hmph. Probably the kettle." },
    family: { name: "Xochi", role: "the Night Watch", img: "/static/characters/xochi.svg",
      bio: "A xoloitzcuintli, the dog that guides souls on Día de los Muertos. She keeps watch all night and writes the family a note at dawn.",
      line: "I kept watch. Here is what I saw." },
  };
  const ZONES = [
    { upto: 4, name: "calm", color: "#2ec4b6" },
    { upto: 6, name: "a whisper", color: "#ffbf3c" },
    { upto: 10, name: "poltergeist", color: "#ff9f1c" },
    { upto: 16, name: "full apparition", color: "#e83f8b" },
  ];
  const zoneOf = (s) => ZONES.find((z) => s < z.upto) || ZONES[ZONES.length - 1];
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let state = { nights: [], byDate: {}, current: null, mode: "medium" };

  const level = (score) => (score >= 10 ? 3 : score >= 6 ? 2 : score >= 4 ? 1 : 0);
  const fmtVal = (v, unit) => (unit === "Wh" ? `${Math.round(v)} Wh` : unit === "on/off" ? (v >= 0.5 ? "on" : "off") : `${Number(v).toFixed(1)} ${unit}`);
  const longDate = (iso, weekday) => {
    const [y, m, d] = iso.split("-").map(Number);
    return `${weekday}, ${d} ${MONTHS[m - 1]} ${y}`;
  };

  async function getJSON(url, opts) {
    const r = await fetch(url, opts);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(body.detail || r.statusText), { status: r.status });
    return body;
  }

  // ------------------------------------------------------------ decorations
  function papelPicado() {
    const w = Math.max(window.innerWidth, 360);
    const fw = 64, n = Math.ceil(w / fw) + 1;
    const colors = ["#e83f8b", "#ff9f1c", "#2ec4b6", "#a77bff", "#ffbf3c"];
    const hole = "#140d2b";
    let flags = "";
    for (let i = 0; i < n; i++) {
      const x = i * fw + 2, c = colors[i % colors.length], d = (i % 5) * 0.35;
      let zig = "";
      for (let k = 0; k <= 6; k++) zig += ` L${x + 58 - k * 9.6},${k % 2 ? 66 : 74}`;
      flags += `<g class="flag" style="animation-delay:-${d}s">
        <path d="M${x},10 L${x + 58},10${zig} L${x},74 Z" fill="${c}" opacity=".92"/>
        <circle cx="${x + 29}" cy="34" r="8" fill="${hole}"/>
        <path d="M${x + 29},20 l4,6 l-4,6 l-4,-6 Z M${x + 15},34 l5,4 l-5,4 l-5,-4 Z M${x + 43},34 l5,4 l-5,4 l-5,-4 Z" fill="${hole}"/>
        <circle cx="${x + 12}" cy="56" r="3" fill="${hole}"/><circle cx="${x + 29}" cy="56" r="3.5" fill="${hole}"/><circle cx="${x + 46}" cy="56" r="3" fill="${hole}"/>
      </g>`;
    }
    $("#papel").innerHTML = `<svg viewBox="0 0 ${n * fw} 96" preserveAspectRatio="xMinYMin slice"><path d="M0,10 L${n * fw},10" stroke="#fbf3e4" stroke-width="2" opacity=".7"/>${flags}</svg>`;
  }

  function drifts() {
    if (reduceMotion) return;
    const petal = (c) => `<svg width="18" height="18" viewBox="0 0 20 20"><ellipse cx="10" cy="10" rx="5" ry="9" fill="${c}"/></svg>`;
    const bat = `<svg width="30" height="16" viewBox="0 0 30 16"><path d="M15 6 C12 0 6 2 0 3 C4 6 4 10 8 9 C9 12 12 12 15 10 C18 12 21 12 22 9 C26 10 26 6 30 3 C24 2 18 0 15 6 Z" fill="#0d0820" opacity=".8"/></svg>`;
    const items = [];
    for (let i = 0; i < 14; i++) items.push(i % 5 === 4 ? bat : petal(["#ff9f1c", "#ffbf3c", "#e83f8b"][i % 3]));
    $("#drifts").innerHTML = items.map((svg, i) => {
      const left = (i * 73) % 100, dur = 14 + (i * 7) % 12, delay = -((i * 3.7) % dur);
      return `<div class="drift" style="left:${left}vw;animation-duration:${dur}s;animation-delay:${delay}s">${svg}</div>`;
    }).join("");
  }

  function ofrenda() {
    const candle = (x, h) => `<rect x="${x}" y="${92 - h}" width="16" height="${h}" rx="3" fill="#fbf3e4" stroke="#2a2048" stroke-width="3"/>
      <path class="flame" d="M${x + 8},${68 - h + 20} q7,9 0,14 q-7,-5 0,-14 Z" fill="#ff9f1c" stroke="#c2410c" stroke-width="1.5"/>`;
    const marigold = (x, y, c) => `<circle cx="${x}" cy="${y}" r="11" fill="${c}" stroke="#2a2048" stroke-width="2.5"/><circle cx="${x}" cy="${y}" r="5" fill="#c2410c"/>`;
    const pumpkin = (x) => `<g stroke="#2a2048" stroke-width="3"><ellipse cx="${x}" cy="80" rx="30" ry="22" fill="#ff9f1c"/><path d="M${x - 10},60 Q${x},80 ${x - 10},100 M${x + 10},60 Q${x},80 ${x + 10},100" fill="none"/><path d="M${x},58 l3,-10" stroke-width="5"/></g>
      <path d="M${x - 14},76 l6,-6 l6,6 Z M${x + 2},76 l6,-6 l6,6 Z M${x - 12},86 q12,8 24,0" fill="#2a2048"/>`;
    const skull = (x) => `<g stroke="#2a2048" stroke-width="3"><path d="M${x - 20},78 a20,20 0 1 1 40,0 v8 h-8 v6 h-24 v-6 h-8 Z" fill="#fbf3e4"/></g>
      <circle cx="${x - 8}" cy="76" r="6" fill="#e83f8b"/><circle cx="${x + 8}" cy="76" r="6" fill="#2ec4b6"/><path d="M${x},84 l-3,4 h6 Z" fill="#2a2048"/>`;
    $("#ofrenda").innerHTML = `<rect x="0" y="100" width="760" height="18" rx="4" fill="#7a3fd1" stroke="#2a2048" stroke-width="3"/>
      ${candle(40, 40)}${candle(70, 54)}${marigold(110, 92, "#ffbf3c")}${marigold(132, 96, "#ff9f1c")}${pumpkin(200)}${marigold(262, 94, "#e83f8b")}
      ${candle(300, 46)}${skull(370)}${candle(430, 60)}${marigold(470, 94, "#ff9f1c")}${pumpkin(540)}${marigold(600, 96, "#ffbf3c")}${candle(640, 50)}${candle(672, 36)}${marigold(712, 94, "#e83f8b")}`;
  }

  function crewCards() {
    $("#crew").innerHTML = Object.entries(CREW).map(([k, c]) => `<div class="card ${k}">
        <img src="${c.img}" alt="${esc(c.name)}, ${esc(c.role)}">
        <div><div class="role">${esc(c.role)}</div><h3>${esc(c.name)}</h3><p>${esc(c.bio)}</p><q>${esc(c.line)}</q></div>
      </div>`).join("");
  }

  // ------------------------------------------------------------ haunting map
  function renderCalendar() {
    const el = $("#calendar");
    if (!state.nights.length) {
      el.innerHTML = '<span class="loading">No nights scanned yet. Run <code>witching-hour scan</code>.</span>';
      return;
    }
    const months = {};
    for (const n of state.nights) (months[n.night.slice(0, 7)] ||= []).push(n);
    el.innerHTML = "";
    for (const [ym] of Object.entries(months)) {
      const [y, m] = ym.split("-").map(Number);
      const box = document.createElement("div");
      box.className = "month";
      box.innerHTML = `<h3>${MONTHS[m - 1]} ${y}</h3>`;
      const grid = document.createElement("div");
      grid.className = "grid";
      const first = new Date(Date.UTC(y, m - 1, 1));
      const offset = (first.getUTCDay() + 6) % 7;
      for (let i = 0; i < offset; i++) grid.appendChild(Object.assign(document.createElement("span"), { className: "cell empty" }));
      const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
      for (let d = 1; d <= days; d++) {
        const iso = `${ym}-${String(d).padStart(2, "0")}`;
        const n = state.byDate[iso];
        const b = document.createElement("button");
        if (!n) {
          b.className = "cell none";
          b.disabled = true;
          b.title = `${iso}: not scanned`;
        } else {
          b.className = `cell l${level(n.score)}${n.n_cold ? " cold" : ""}`;
          b.title = `${iso}: ${n.headline} (${n.score} sigma)${n.n_cold ? " · a room stayed below 18 °C" : ""}`;
          b.setAttribute("aria-label", `${longDate(iso, n.weekday)}: ${n.headline}`);
          b.dataset.night = iso;
          b.addEventListener("click", () => openNight(iso));
        }
        grid.appendChild(b);
      }
      box.appendChild(grid);
      el.appendChild(box);
    }
    const top = [...state.nights].filter((n) => n.stories && n.stories.length).sort((a, b) => b.score - a.score).slice(0, 6);
    $("#top-nights").innerHTML = top.length ? "<span class='sub' style='margin:0'>Open case files:</span>" : "";
    for (const n of top) {
      const c = document.createElement("button");
      c.className = "chip";
      c.textContent = `${n.night} · ${n.headline}`;
      c.addEventListener("click", () => openNight(n.night));
      $("#top-nights").appendChild(c);
    }
  }

  // ------------------------------------------------------------ spirit meter
  function meterSVG(score) {
    const cx = 110, cy = 108, r = 86;
    const pt = (v, rr = r) => {
      const a = Math.PI * (1 - Math.min(v, 16) / 16);
      return [cx + rr * Math.cos(a), cy - rr * Math.sin(a)];
    };
    let lo = 0, arcs = "";
    for (const z of ZONES) {
      const [x0, y0] = pt(lo), [x1, y1] = pt(z.upto);
      arcs += `<path d="M${x0.toFixed(1)},${y0.toFixed(1)} A${r},${r} 0 0 1 ${x1.toFixed(1)},${y1.toFixed(1)}" stroke="${z.color}" stroke-width="18" fill="none"/>`;
      lo = z.upto;
    }
    const ang = -90 + 180 * Math.min(score, 16) / 16;
    return `<svg viewBox="0 0 220 124" role="img" aria-label="Spirit meter at ${esc(score)} sigma">
      ${arcs}
      <g class="needle" style="transform: rotate(${reduceMotion ? ang : -90}deg)" data-angle="${ang}">
        <path d="M${cx - 4},${cy} L${cx},${cy - 78} L${cx + 4},${cy} Z" fill="#fbf3e4" stroke="#2a2048" stroke-width="2"/>
      </g>
      <circle cx="${cx}" cy="${cy}" r="9" fill="#a77bff" stroke="#2a2048" stroke-width="3"/>
      <text x="22" y="122" fill="#b9add8" font-size="10">calm</text><text x="168" y="122" fill="#b9add8" font-size="10">apparition</text>
    </svg>`;
  }

  // ------------------------------------------------------------ case file
  async function openNight(iso, push = true) {
    document.querySelectorAll(".cell.selected").forEach((c) => c.classList.remove("selected"));
    const cell = document.querySelector(`.cell[data-night="${iso}"]`);
    if (cell) cell.classList.add("selected");
    const sec = $("#night");
    sec.innerHTML = '<p class="loading">Lighting the candles...</p>';
    try {
      state.current = await getJSON(`/api/nights/${iso}`);
    } catch (e) {
      sec.innerHTML = `<p class="notice">Could not open ${esc(iso)}: ${esc(e.message)}</p>`;
      return;
    }
    if (push) history.replaceState(null, "", `#${iso}`);
    renderNight();
    if (push) sec.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  }

  function storyHTML(night) {
    const c = CREW[state.mode];
    const story = night.stories && night.stories[state.mode];
    const who = `<div class="who"><img src="${c.img}" alt="${esc(c.name)}, ${esc(c.role)}"><div class="name">${esc(c.name)}</div><div class="line">"${esc(c.line)}"</div></div>`;
    if (!story) {
      return `<div class="scene">${who}<div class="bubble ${state.mode}"><p>${esc(c.name)} has not written about this night yet. The apparitions and the charts are still real.</p></div></div>`;
    }
    const sentences = story.sentences
      .map((s) => `${esc(s.text)}${(s.cites || []).map((ci) => ` <button class="cite" data-ev="${esc(ci)}" title="show ${esc(ci)}">${esc(ci)}</button>`).join("")}`)
      .join(" ");
    const total = story.sentences.length + (story.rejected || []).length;
    const dropped = story.rejected && story.rejected.length
      ? `<details class="dropped"><summary>${story.rejected.length} sentence(s) vanished: no proof</summary><ul>${story.rejected
          .map((r) => `<li>"${esc(r.text)}" <em>(${esc(r.reason)})</em></li>`).join("")}</ul></details>` : "";
    const audio = story.audio ? `<audio class="voice" controls preload="none" src="${esc(story.audio)}"></audio>` : "";
    return `<div class="scene">${who}
      <div class="bubble ${state.mode}">
        <h3>${esc(story.title)}</h3>
        <p>${sentences}</p>
        ${audio}
        <div class="verify"><b>${story.sentences.length} of ${total}</b> sentences backed by the sensors · voice of ${esc(c.name)} by ${esc(story.model)}${story.audio ? " · read aloud with ElevenLabs" : ""}</div>
        ${dropped}
      </div></div>`;
  }

  function checksHTML(night) {
    return (night.checks || []).map((c) => `<div class="event check" id="ev-${esc(c.id)}" data-ev="${esc(c.id)}">
        <div class="top"><span><span class="id">${esc(c.id)}</span> <span class="what">cold room: ${esc(c.room)} ${esc(c.rule)}</span></span><span>${esc(c.start)} to ${esc(c.end)}</span></div>
        <div class="nums">coldest <b>${esc(Number(c.coldest).toFixed(1))} °C</b> at ${esc(c.coldest_time)} · ${esc(c.minutes)} minutes · WHO recommends at least 18 °C indoors in cold seasons</div>
      </div>`).join("");
  }

  function eventsHTML(night) {
    if (!night.events.length) return '<p class="notice">No apparitions: every reading stayed inside the range the spirit meter expected.</p>';
    return night.events.slice().sort((a, b) => b.sigma - a.sigma).slice(0, 10).sort((a, b) => a.start.localeCompare(b.start))
      .map((e) => `<div class="event" id="ev-${esc(e.id)}" data-ev="${esc(e.id)}">
        <div class="top"><span><span class="id">apparition ${esc(e.id)}</span> <span class="what">${esc(e.room)}: ${esc(PHENOMENA[`${e.kind}|${e.direction}`] || "a strange reading")}</span></span><span>${esc(e.start)} to ${esc(e.end)}</span></div>
        <div class="nums">observed <b>${esc(fmtVal(e.observed, e.unit))}</b> at ${esc(e.peak_time)} · expected ${esc(fmtVal(e.expected, e.unit))} (90% range ${esc(fmtVal(e.expected_low, e.unit))} to ${esc(fmtVal(e.expected_high, e.unit))}) · ${esc(e.sigma)} sigma</div>
      </div>`).join("");
  }

  function chartSVG(sid, night) {
    const s = night.series[sid];
    const meta = night.sensors[sid];
    const W = 600, H = 150, L = 40, R = 8, T = 10, B = 22;
    const n = s.t.length;
    const all = [...s.y, ...s.q05, ...s.q95];
    let lo = Math.min(...all), hi = Math.max(...all);
    if (hi - lo < 1e-6) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.08;
    lo -= pad; hi += pad;
    const x = (i) => L + (i / (n - 1)) * (W - L - R);
    const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const line = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const band = `M${s.q95.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("L")}L${s.q05.map((v, i) => [i, v]).reverse().map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("L")}Z`;
    const idx = (t) => Math.max(0, s.t.indexOf(t));
    const spans = night.events.filter((e) => e.sensor === sid).map((e) => {
      const a = idx(e.start), endIdx = s.t.indexOf(e.end), b = endIdx < 0 ? n - 1 : endIdx;
      const x0 = x(a) - 3, x1 = Math.max(x(b) - 3, x0 + 6);
      return `<rect class="span" data-ev="${esc(e.id)}" x="${x0.toFixed(1)}" y="${T}" width="${(x1 - x0).toFixed(1)}" height="${H - T - B}"><title>${esc(e.id)}</title></rect>`;
    }).join("");
    const ticks = [];
    s.t.forEach((t, i) => { if (t.endsWith(":00")) ticks.push(`<text class="axis" x="${x(i).toFixed(1)}" y="${H - 6}" text-anchor="middle">${esc(t.slice(0, 2))}h</text><line class="grid-line" x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${T}" y2="${H - B}"/>`); });
    const yt = [lo + pad, hi - pad].map((v) => `<text class="axis" x="${L - 4}" y="${(y(v) + 3).toFixed(1)}" text-anchor="end">${meta.unit === "Wh" ? Math.round(v) : v.toFixed(1)}</text>`).join("");
    return `<div class="chart"><div class="label"><span>${esc(meta.label)}</span><span>${esc(meta.unit)}</span></div>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(meta.label)}: observed vs the spirit meter's expected range">
        ${ticks.join("")}${spans}<path class="band" d="${band}"/><path class="med" d="${line(s.q50)}"/><path class="obs" d="${line(s.y)}"/>${yt}
      </svg></div>`;
  }

  function renderNight() {
    const night = state.current;
    const sensors = [...new Set(night.events.slice().sort((a, b) => b.sigma - a.sigma).map((e) => e.sensor))].slice(0, 4);
    if (!sensors.length) sensors.push(...Object.keys(night.series).slice(0, 2));
    const z = zoneOf(night.score);
    $("#night").innerHTML = `
      <div class="case-head">
        <div><div class="stamp">Case file · ${esc(night.n_events)} apparition${night.n_events === 1 ? "" : "s"}${(night.checks || []).length ? ` · ${night.checks.length} cold room${night.checks.length === 1 ? "" : "s"}` : ""}</div>
        <h2>${esc(longDate(night.night, night.weekday))} · 00:00 to 06:00</h2></div>
        <div class="meter">${meterSVG(night.score)}<div class="reading" style="color:${z.color}">${esc(night.score)} sigma</div><div class="zone">spirit meter: ${esc(z.name)}</div></div>
      </div>
      <div class="tabs" role="group" aria-label="Who tells the story">
        ${Object.entries(CREW).map(([k, c]) => `<button class="tab ${k}" aria-pressed="${state.mode === k}" data-mode="${k}"><img src="${c.img}" alt="">${esc(c.name)}</button>`).join("")}
      </div>
      <div class="layout">
        <div>
          ${storyHTML(night)}
          <h3 class="locker">🗝️ Evidence locker</h3>
          <div class="events">${eventsHTML(night)}${checksHTML(night)}</div>
        </div>
        <div>
          <div class="charts">${sensors.map((sid) => chartSVG(sid, night)).join("")}</div>
          <div class="key"><span><i style="background:var(--ghost)"></i>what the sensor felt</span><span><i style="background:var(--band)"></i>spirit meter's 90% range</span><span><i style="border-top:2px dashed var(--violet);height:0"></i>expected</span><span><i style="background:rgba(255,159,28,.3)"></i>apparition</span></div>
        </div>
      </div>`;
    const needle = $("#night .needle");
    if (needle && !reduceMotion) requestAnimationFrame(() => requestAnimationFrame(() => { needle.style.transform = `rotate(${needle.dataset.angle}deg)`; }));
    $("#night").querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { state.mode = b.dataset.mode; renderNight(); }));
    $("#night").querySelectorAll("[data-ev]").forEach((el) => {
      const on = () => highlight(el.dataset.ev, true);
      const off = () => highlight(el.dataset.ev, false);
      el.addEventListener("mouseenter", on);
      el.addEventListener("mouseleave", off);
      el.addEventListener("focus", on);
      el.addEventListener("blur", off);
      if (el.classList.contains("cite")) el.addEventListener("click", () => document.getElementById(`ev-${el.dataset.ev}`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
    });
  }

  function highlight(id, on) {
    document.querySelectorAll(`[data-ev="${CSS.escape(id)}"]`).forEach((el) => el.classList.toggle("on", on));
  }

  // ------------------------------------------------------------ agent
  function runHTML(run) {
    const steps = run.steps.map((s) => `<li>${esc(s.tool)}(${esc(JSON.stringify(s.args))})</li>`).join("");
    return `<div class="run"><div class="q">🔮 ${esc(run.question)}</div><ol>${steps}</ol><p class="a">${esc(run.answer)}</p><div class="model">${esc(run.model || "")}</div></div>`;
  }

  async function loadRuns() {
    try {
      const runs = await getJSON("/api/agent-runs");
      $("#runs").innerHTML = runs.length ? `<p class="notice">Recorded hunts (the same agent, Gemma 4 running locally):</p>${runs.map(runHTML).join("")}` : "";
    } catch (_) { /* optional */ }
  }

  $("#ask-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const q = $("#q").value.trim();
    if (q.length < 3) return;
    $("#ask-notice").textContent = "The crew is consulting the sensors...";
    try {
      const run = await getJSON("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      $("#ask-notice").textContent = "";
      $("#runs").insertAdjacentHTML("afterbegin", runHTML(run));
    } catch (e) {
      $("#ask-notice").textContent = e.message;
    }
  });

  // ------------------------------------------------------------ eval, bake-off, tonight
  async function loadEval() {
    try {
      const ev = await getJSON("/api/eval");
      if (!ev.results) { $("#eval").innerHTML = '<p class="notice">Benchmark not run yet.</p>'; return; }
      const best = Math.max(...ev.results.map((r) => r.recall_fpr5));
      const strengths = Object.keys(ev.results[0].recall_fpr5_by_strength);
      const ci = (a, pct) => (a ? ` <span class="ci">[${esc(pct ? Math.round(a[0] * 100) : a[0])}, ${esc(pct ? Math.round(a[1] * 100) : a[1])}]</span>` : "");
      $("#eval").innerHTML = `<table><thead><tr><th>Meter</th><th>Ghosts caught (5% false alarms)</th>${strengths.map((s) => `<th>ghost size ${esc(s)}x</th>`).join("")}<th>AUC</th><th>Found the right time</th><th>90% band coverage</th></tr></thead><tbody>${ev.results
        .map((r) => `<tr class="${r.recall_fpr5 === best ? "best" : ""}"><td>${esc(r.backend)}</td><td class="num">${(r.recall_fpr5 * 100).toFixed(0)}%${ci(r.recall_fpr5_ci95, true)}</td>${strengths.map((s) => `<td class="num">${(r.recall_fpr5_by_strength[s] * 100).toFixed(0)}%</td>`).join("")}<td class="num">${r.auc.toFixed(3)}${ci(r.auc_ci95, false)}</td><td class="num">${(r.located * 100).toFixed(0)}%</td><td class="num">${(r.coverage90 * 100).toFixed(0)}%</td></tr>`)
        .join("")}</tbody></table><p class="notice">${ev.results[0].n_cases} planted ghosts on ${ev.nights.length} real nights, sensors ${esc(ev.sensors.join(", "))}. Ghost size is a multiple of the sensor's typical night-time wobble. A perfectly calibrated 90% band covers 90% of real readings. Brackets: 95% bootstrap intervals.</p>`;
    } catch (_) {
      $("#eval").innerHTML = '<p class="notice">Benchmark not available.</p>';
    }
  }

  async function loadBakeoff() {
    try {
      const b = await getJSON("/api/bakeoff");
      if (!b.results || !b.results.length) return;
      const rows = [...b.results].sort((x, y) => y.grounded_share - x.grounded_share);
      const best = rows[0].grounded_share;
      const local = b.local && b.local.stories ? `<tr class="best"><td>${esc(b.local.model)} <span class="ci">(${esc(b.local.via)})</span></td><td class="num">${esc(Math.round(b.local.grounded_share * 100))}%</td><td class="num">${esc(b.local.verified)} / ${esc(b.local.sentences)}</td><td class="num">${esc(b.local.stories)}</td><td></td></tr>` : "";
      $("#bakeoff").innerHTML = `<table><thead><tr><th>Model</th><th>Sentences backed by the sensors</th><th>Verified / written</th><th>Stories</th><th>Avg seconds</th></tr></thead><tbody>${local}${rows
        .map((r) => `<tr class="${r.grounded_share === best && !local ? "best" : ""}"><td>${esc(r.model)}</td><td class="num">${esc(Math.round(r.grounded_share * 100))}%</td><td class="num">${esc(r.verified)} / ${esc(r.sentences)}</td><td class="num">${esc(r.stories)}${r.failed ? ` (+${esc(r.failed)} not valid JSON)` : ""}</td><td class="num">${esc(r.avg_seconds)}</td></tr>`)
        .join("")}</tbody></table><p class="notice">${esc(b.nights.length)} nights × ${esc(b.modes.join(" and "))}. A sentence counts when every number and time in it matches what it cites.</p>`;
      $("#bakeoff-sec").hidden = false;
    } catch (_) { /* optional */ }
  }

  async function loadTonight() {
    try {
      const t = await getJSON("/api/tonight");
      if (!t.rooms || !t.rooms.length) return;
      const out = t.hours.map((h) => `${esc(h.time)} ${esc(h.temp_c)} °C`).join(" · ");
      $("#tonight-sub").textContent = `Xochi checked the live weather for ${t.place} (${t.source}, fetched ${t.fetched_at}) and asked the spirit meter how each room will feel, learned from ${t.trained_on}.`;
      $("#tonight-body").innerHTML = `<p class="notice" style="margin-top:0">Outside tonight: ${out}</p>
        <div class="table-wrap"><table><thead><tr><th>Room</th><th>Coldest expected</th><th>90% range</th><th>Chance below 18 °C</th></tr></thead><tbody>${t.rooms
          .map((r) => `<tr class="${r.p_below_18 >= 0.5 ? "best" : ""}"><td>${esc(r.room)}</td><td class="num">${esc(r.expected)} °C at ${esc(r.coldest_time)}</td><td class="num">${esc(r.low)} to ${esc(r.high)} °C</td><td class="num">${esc((r.p_below_18 * 100).toFixed(1))}%</td></tr>`)
          .join("")}</tbody></table></div><p class="notice">A forecast, not a reading: the demo house's logs end in 2016, so this is how that house would feel under tonight's weather.</p>`;
      $("#tonight").hidden = false;
    } catch (_) { /* optional */ }
  }

  async function loadField() {
    try {
      const f = await getJSON("/api/fieldwork");
      if (!f.url) return;
      const verdict = f.cold_warning ? "There IS an official cold warning. Even I will not blame a kettle tonight." : "No official cold warning. Hmph. If a room goes cold, check the heating before you call a priest.";
      $("#field-body").innerHTML = `<h3 style="margin:0 0 6px">Dr. Bigotes's field trip</h3>
        <p class="notice" style="margin-top:0">He opened the official warnings page in a real cloud browser (${esc(f.via)}, ${esc(f.fetched_at)}): <a href="${esc(f.url)}">${esc(f.url)}</a></p>
        <p><b>"${esc(verdict)}"</b></p>
        ${f.excerpt ? `<p class="notice">What the page said: ${esc(f.excerpt.slice(0, 280))}${f.excerpt.length > 280 ? "..." : ""}</p>` : ""}
        ${f.screenshot ? `<img src="/media/fieldwork.png" alt="Screenshot of the official warnings page taken in the Browserbase browser" style="width:100%;height:auto;border-radius:12px;border:2px solid var(--line);margin-top:8px">` : ""}`;
      $("#field").hidden = false;
    } catch (_) { /* optional */ }
  }

  // ------------------------------------------------------------ boot
  async function boot() {
    papelPicado();
    drifts();
    ofrenda();
    crewCards();
    window.addEventListener("resize", () => { clearTimeout(boot._t); boot._t = setTimeout(papelPicado, 200); });
    try {
      const idx = await getJSON("/api/nights");
      state.nights = idx.nights || [];
      state.byDate = Object.fromEntries(state.nights.map((n) => [n.night, n]));
      if (idx.meta && idx.meta.attribution) $("#attribution").textContent = `Data: ${idx.meta.attribution}`;
    } catch (e) {
      $("#calendar").innerHTML = `<span class="notice">Could not load nights: ${esc(e.message)}</span>`;
    }
    renderCalendar();
    loadRuns();
    loadEval();
    loadTonight();
    loadBakeoff();
    loadField();
    try {
      const h = await getJSON("/api/health");
      if (!h.live) $("#ask-notice").textContent = "Live questions are off on this public demo (a house's night logs are private). Below are hunts recorded with Gemma 4 running locally.";
    } catch (_) { /* ignore */ }
    const fromHash = location.hash.slice(1);
    const start = state.byDate[fromHash] ? fromHash
      : ([...state.nights].filter((n) => n.stories && n.stories.length).sort((a, b) => b.score - a.score)[0] || [...state.nights].sort((a, b) => b.score - a.score)[0] || {}).night;
    if (start) openNight(start, !!state.byDate[fromHash]);
  }

  boot();
})();
