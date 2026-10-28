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

  // ------------------------------------------------------------ calendar
  function renderCalendar() {
    const el = $("#calendar");
    if (!state.nights.length) {
      el.innerHTML = '<span class="loading">No nights scanned yet. Run <code>witching-hour scan</code>.</span>';
      return;
    }
    const months = {};
    for (const n of state.nights) (months[n.night.slice(0, 7)] ||= []).push(n);
    el.innerHTML = "";
    for (const [ym, list] of Object.entries(months)) {
      const [y, m] = ym.split("-").map(Number);
      const box = document.createElement("div");
      box.className = "month";
      box.innerHTML = `<h3>${MONTHS[m - 1]} ${y}</h3>`;
      const grid = document.createElement("div");
      grid.className = "grid";
      const first = new Date(Date.UTC(y, m - 1, 1));
      const offset = (first.getUTCDay() + 6) % 7; // Monday first
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
          b.className = `cell l${level(n.score)}`;
          b.title = `${iso}: ${n.headline} (${n.score} sigma)`;
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
    $("#top-nights").innerHTML = top.length ? "<span class='sub' style='margin:0'>Nights with stories:</span>" : "";
    for (const n of top) {
      const c = document.createElement("button");
      c.className = "chip";
      c.textContent = `${n.night} · ${n.headline}`;
      c.addEventListener("click", () => openNight(n.night));
      $("#top-nights").appendChild(c);
    }
  }

  // ------------------------------------------------------------ night
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
    sec.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function storyHTML(night) {
    const story = night.stories && night.stories[state.mode];
    if (!story) {
      return `<div class="story ${state.mode}"><p class="notice">No ${state.mode} story was written for this night yet. The events and charts are still real.</p></div>`;
    }
    const sentences = story.sentences
      .map((s) => `${esc(s.text)}${(s.cites || []).map((c) => ` <button class="cite" data-ev="${esc(c)}" title="show ${esc(c)}">${esc(c)}</button>`).join("")}`)
      .join(" ");
    const dropped = story.rejected && story.rejected.length
      ? `<details class="dropped"><summary>${story.rejected.length} sentence(s) dropped by the validator</summary><ul>${story.rejected
          .map((r) => `<li>"${esc(r.text)}" <em>(${esc(r.reason)})</em></li>`).join("")}</ul></details>`
      : "";
    return `<div class="story ${state.mode}">
      <h3>${esc(story.title)}</h3>
      <p>${sentences}</p>
      ${story.audio ? `<audio class="voice" controls preload="none" src="${esc(story.audio)}"></audio><div class="verify">Read aloud with ElevenLabs, verified sentences only.</div>` : ""}
      <div class="verify"><b>${story.sentences.length} of ${story.sentences.length + (story.rejected || []).length}</b> sentences verified against the sensor events · narrated by ${esc(story.model)}</div>
      ${dropped}
    </div>`;
  }

  function checksHTML(night) {
    return (night.checks || []).map((c) => `<div class="event check" id="ev-${esc(c.id)}" data-ev="${esc(c.id)}">
        <div class="top"><span><span class="id">${esc(c.id)}</span> <span class="what">${esc(c.room)}: ${esc(c.rule)}</span></span><span>${esc(c.start)} to ${esc(c.end)}</span></div>
        <div class="nums">coldest <b>${esc(Number(c.coldest).toFixed(1))} °C</b> at ${esc(c.coldest_time)} · ${esc(c.minutes)} minutes · WHO recommends at least 18 °C indoors in cold seasons</div>
      </div>`).join("");
  }

  function eventsHTML(night) {
    if (!night.events.length) return '<p class="notice">Every reading stayed inside the range TabPFN expected. A quiet night.</p>';
    return night.events
      .slice()
      .sort((a, b) => b.sigma - a.sigma)
      .slice(0, 10)
      .sort((a, b) => a.start.localeCompare(b.start))
      .map((e) => `<div class="event" id="ev-${esc(e.id)}" data-ev="${esc(e.id)}">
        <div class="top"><span><span class="id">${esc(e.id)}</span> <span class="what">${esc(e.room)}: ${esc(PHENOMENA[`${e.kind}|${e.direction}`] || "a strange reading")}</span></span><span>${esc(e.start)} to ${esc(e.end)}</span></div>
        <div class="nums">observed <b>${esc(fmtVal(e.observed, e.unit))}</b> at ${esc(e.peak_time)} · expected ${esc(fmtVal(e.expected, e.unit))} (90% range ${esc(fmtVal(e.expected_low, e.unit))} to ${esc(fmtVal(e.expected_high, e.unit))}) · ${esc(e.sigma)} sigma</div>
      </div>`)
      .join("");
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
      const a = idx(e.start);
      const endIdx = s.t.indexOf(e.end);
      const b = endIdx < 0 ? n - 1 : endIdx;
      const x0 = x(a) - 3, x1 = Math.max(x(b) - 3, x0 + 6);
      return `<rect class="span" data-ev="${esc(e.id)}" x="${x0.toFixed(1)}" y="${T}" width="${(x1 - x0).toFixed(1)}" height="${H - T - B}"><title>${esc(e.id)}</title></rect>`;
    }).join("");
    const ticks = [];
    s.t.forEach((t, i) => { if (t.endsWith(":00")) ticks.push(`<text class="axis" x="${x(i).toFixed(1)}" y="${H - 6}" text-anchor="middle">${esc(t.slice(0, 2))}h</text><line class="grid-line" x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${T}" y2="${H - B}"/>`); });
    const yt = [lo + pad, hi - pad].map((v) => `<text class="axis" x="${L - 4}" y="${(y(v) + 3).toFixed(1)}" text-anchor="end">${meta.unit === "Wh" ? Math.round(v) : v.toFixed(1)}</text>`).join("");
    return `<div class="chart"><div class="label"><span>${esc(meta.label)}</span><span>${esc(meta.unit)}</span></div>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(meta.label)}: observed vs expected range">
        ${ticks.join("")}${spans}<path class="band" d="${band}"/><path class="med" d="${line(s.q50)}"/><path class="obs" d="${line(s.y)}"/>${yt}
      </svg></div>`;
  }

  function renderNight() {
    const night = state.current;
    const sensors = [...new Set(night.events.slice().sort((a, b) => b.sigma - a.sigma).map((e) => e.sensor))].slice(0, 4);
    if (!sensors.length) sensors.push(...Object.keys(night.series).slice(0, 2));
    const hasStories = Object.keys(night.stories || {}).length > 0;
    $("#night").innerHTML = `
      <div class="night-head">
        <h2>${esc(longDate(night.night, night.weekday))} · 00:00 to 06:00</h2>
        <span class="badge ${night.score < 4 ? "calm" : ""}">${esc(night.n_events)} event${night.n_events === 1 ? "" : "s"} · peak ${esc(night.score)} sigma</span>
      </div>
      <div class="modes" role="group" aria-label="Narrator">
        <button class="medium" aria-pressed="${state.mode === "medium"}" data-mode="medium">🕯️ The Medium</button>
        <button class="skeptic" aria-pressed="${state.mode === "skeptic"}" data-mode="skeptic">🔦 The Skeptic</button>
        <button class="family" aria-pressed="${state.mode === "family"}" data-mode="family">💌 Morning note</button>
      </div>
      <div class="layout">
        <div>
          <div class="panel">${hasStories ? storyHTML(night) : '<p class="notice">No story for this night yet. Here is what the sensors say.</p>'}</div>
          <h3 style="margin:18px 0 8px;font-size:16px">The evidence</h3>
          <div class="events">${eventsHTML(night)}${checksHTML(night)}</div>
        </div>
        <div>
          <div class="charts">${sensors.map((sid) => chartSVG(sid, night)).join("")}</div>
          <div class="key"><span><i style="background:var(--ghost)"></i>observed</span><span><i style="background:var(--band)"></i>TabPFN 90% range</span><span><i style="border-top:2px dashed var(--violet);height:0"></i>expected median</span><span><i style="background:rgba(255,181,71,.3)"></i>event</span></div>
        </div>
      </div>`;
    $("#night").querySelectorAll(".modes button").forEach((b) => b.addEventListener("click", () => { state.mode = b.dataset.mode; renderNight(); }));
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
    return `<div class="run"><div class="q">${esc(run.question)}</div><ol>${steps}</ol><p class="a">${esc(run.answer)}</p><div class="model">${esc(run.model || "")}</div></div>`;
  }

  async function loadRuns() {
    try {
      const runs = await getJSON("/api/agent-runs");
      $("#runs").innerHTML = runs.length ? `<p class="notice">Recorded investigations (same agent, Gemma running locally):</p>${runs.map(runHTML).join("")}` : "";
    } catch (_) { /* optional */ }
  }

  $("#ask-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const q = $("#q").value.trim();
    if (q.length < 3) return;
    $("#ask-notice").textContent = "The agent is consulting the sensors...";
    try {
      const run = await getJSON("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      $("#ask-notice").textContent = "";
      $("#runs").insertAdjacentHTML("afterbegin", runHTML(run));
    } catch (e) {
      $("#ask-notice").textContent = e.message;
    }
  });

  // ------------------------------------------------------------ bake-off
  async function loadBakeoff() {
    try {
      const b = await getJSON("/api/bakeoff");
      if (!b.results || !b.results.length) return;
      const rows = [...b.results].sort((x, y) => y.grounded_share - x.grounded_share);
      const best = rows[0].grounded_share;
      const local = b.local && b.local.stories ? `<tr><td>${esc(b.local.model)} <span class="sub">(${esc(b.local.via)})</span></td><td class="num">${esc(Math.round(b.local.grounded_share * 100))}%</td><td class="num">${esc(b.local.verified)} / ${esc(b.local.sentences)}</td><td class="num">${esc(b.local.stories)}</td><td></td></tr>` : "";
      $("#bakeoff").innerHTML = `<table><thead><tr><th>Model</th><th>Grounded sentences</th><th>Verified / written</th><th>Stories</th><th>Avg seconds</th></tr></thead><tbody>${rows
        .map((r) => `<tr class="${r.grounded_share === best ? "best" : ""}"><td>${esc(r.model)}</td><td class="num">${esc(Math.round(r.grounded_share * 100))}%</td><td class="num">${esc(r.verified)} / ${esc(r.sentences)}</td><td class="num">${esc(r.stories)}${r.failed ? ` (+${esc(r.failed)} failed)` : ""}</td><td class="num">${esc(r.avg_seconds)}</td></tr>`)
        .join("")}${local}</tbody></table><p class="notice">${esc(b.nights.length)} nights × ${esc(b.modes.join(" and "))}. A sentence is grounded when every number and time in it matches the event it cites.</p>`;
      $("#bakeoff-sec").hidden = false;
    } catch (_) { /* optional */ }
  }

  // ------------------------------------------------------------ tonight
  async function loadTonight() {
    try {
      const t = await getJSON("/api/tonight");
      if (!t.rooms || !t.rooms.length) return;
      const out = t.hours.map((h) => `${esc(h.time)} ${esc(h.temp_c)} °C`).join(" · ");
      $("#tonight-sub").textContent = `Live weather for ${t.place} (${t.source}, fetched ${t.fetched_at}), and TabPFN's forecast for each room, learned from ${t.trained_on}.`;
      $("#tonight-body").innerHTML = `<p class="notice" style="margin-top:0">Outside: ${out}</p>
        <div class="table-wrap"><table><thead><tr><th>Room</th><th>Coldest expected</th><th>90% range</th><th>Chance below 18 °C</th></tr></thead><tbody>${t.rooms
          .map((r) => `<tr class="${r.p_below_18 >= 0.5 ? "best" : ""}"><td>${esc(r.room)}</td><td class="num">${esc(r.expected)} °C at ${esc(r.coldest_time)}</td><td class="num">${esc(r.low)} to ${esc(r.high)} °C</td><td class="num">${esc(Math.round(r.p_below_18 * 100))}%</td></tr>`)
          .join("")}</tbody></table></div><p class="notice">The WHO recommends at least 18 °C indoors in cold seasons. This is a forecast, not a reading: the demo house's logs end in 2016.</p>`;
      $("#tonight").hidden = false;
    } catch (_) { /* optional */ }
  }

  // ------------------------------------------------------------ eval
  async function loadEval() {
    try {
      const ev = await getJSON("/api/eval");
      if (!ev.results) { $("#eval").innerHTML = '<p class="notice">Benchmark not run yet.</p>'; return; }
      const best = Math.max(...ev.results.map((r) => r.recall_fpr5));
      const strengths = Object.keys(ev.results[0].recall_fpr5_by_strength);
      $("#eval").innerHTML = `<table><thead><tr><th>Model</th><th>Caught (5% false alarms)</th>${strengths.map((s) => `<th>ghost size ${esc(s)}x</th>`).join("")}<th>AUC</th><th>Found the right time</th><th>90% band coverage</th></tr></thead><tbody>${ev.results
        .map((r) => `<tr class="${r.recall_fpr5 === best ? "best" : ""}"><td>${esc(r.backend)}</td><td class="num">${(r.recall_fpr5 * 100).toFixed(0)}%${r.recall_fpr5_ci95 ? ` <span class="ci">[${esc(Math.round(r.recall_fpr5_ci95[0] * 100))}, ${esc(Math.round(r.recall_fpr5_ci95[1] * 100))}]</span>` : ""}</td>${strengths.map((s) => `<td class="num">${(r.recall_fpr5_by_strength[s] * 100).toFixed(0)}%</td>`).join("")}<td class="num">${r.auc.toFixed(3)}${r.auc_ci95 ? ` <span class="ci">[${esc(r.auc_ci95[0])}, ${esc(r.auc_ci95[1])}]</span>` : ""}</td><td class="num">${(r.located * 100).toFixed(0)}%</td><td class="num">${(r.coverage90 * 100).toFixed(0)}%</td></tr>`)
        .join("")}</tbody></table><p class="notice">${ev.results[0].n_cases} planted ghosts on ${ev.nights.length} real nights, sensors ${esc(ev.sensors.join(", "))}. Ghost size is a multiple of the sensor's typical night-time wobble. A perfectly calibrated 90% band covers 90% of real readings. Brackets: 95% bootstrap intervals over the planted cases.</p>`;
    } catch (_) {
      $("#eval").innerHTML = '<p class="notice">Benchmark not available.</p>';
    }
  }

  // ------------------------------------------------------------ boot
  async function boot() {
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
    try {
      const h = await getJSON("/api/health");
      if (!h.live) $("#ask-notice").textContent = "Live questions are off on this public demo (a house's night logs are private). Below are investigations recorded with Gemma running locally.";
    } catch (_) { /* ignore */ }
    const fromHash = location.hash.slice(1);
    const start = state.byDate[fromHash] ? fromHash
      : ([...state.nights].filter((n) => n.stories && n.stories.length).sort((a, b) => b.score - a.score)[0] || [...state.nights].sort((a, b) => b.score - a.score)[0] || {}).night;
    if (start) openNight(start, false);
  }

  boot();
})();
