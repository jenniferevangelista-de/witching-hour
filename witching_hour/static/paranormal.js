// PARANORMAL.exe: the crew's terminal for The Unheard (a recording) and The Room (live).
// The recording and the camera never leave this page: the browser measures light, motion and
// sound, and only the list of moments (the evidence) goes to the spirit board.
(() => {
  "use strict";
  const WH = window.WH;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = WH.esc;
  const STEP = 0.25, W = 160, H = 90;
  const sleep = (ms) => new Promise((r) => setTimeout(r, WH.reduceMotion ? 0 : ms));

  // ------------------------------------------------------------ measuring (same as witching_hour/footage.py)
  const median = (a) => { const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  function robustZ(x) {
    const med = median(x);
    const mad = median(x.map((v) => Math.abs(v - med))) * 1.4826;
    return x.map((v) => (v - med) / Math.max(mad, 1e-6));
  }
  const whereOf = (cx) => (cx == null ? null : cx < 0.36 ? "left" : cx > 0.64 ? "right" : "center");

  function frameStats(ctx, prev) {
    const d = ctx.getImageData(0, 0, W, H).data;
    const g = new Float32Array(W * H);
    let sum = 0;
    for (let i = 0, j = 0; i < d.length; i += 4, j++) { g[j] = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]; sum += g[j]; }
    const row = { brightness: sum / g.length / 255, motion: 0, area: 0, cx: null };
    if (prev) {
      let diff = 0, n = 0, xs = 0;
      for (let j = 0; j < g.length; j++) {
        const dv = Math.abs(g[j] - prev[j]);
        diff += dv;
        if (dv > 25) { n++; xs += j % W; }
      }
      row.motion = diff / g.length / 255;
      row.area = n / g.length;
      if (row.area > 0.002) row.cx = xs / n / W;
    }
    return [row, g];
  }

  async function frameFeatures(video, maxSec, onProgress) {
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const ctx = c.getContext("2d", { willReadFrequently: true });
    const dur = Math.min(video.duration || 0, maxSec);
    const rows = [];
    let prev = null;
    for (let t = 0; t < dur; t += STEP) {
      if (rows.length >= 8 && rows.slice(1).every((r) => r.motion === 0)) {
        // the frames are not being painted (a background tab): stop seeking, keep the time base for the sound
        const last = rows[rows.length - 1];
        rows.push({ ...last, t: Math.round(t * 100) / 100 });
        continue;
      }
      await new Promise((res) => { video.addEventListener("seeked", res, { once: true }); video.currentTime = t; });
      if (video.requestVideoFrameCallback) {
        await Promise.race([new Promise((res) => video.requestVideoFrameCallback(() => res())), new Promise((res) => setTimeout(res, 250))]);
      }
      ctx.drawImage(video, 0, 0, W, H);
      const [row, g] = frameStats(ctx, prev);
      row.t = Math.round(t * 100) / 100;
      rows.push(row);
      prev = g;
      onProgress && onProgress(t / dur);
    }
    return rows;
  }

  async function audioLevels(buf, maxSec) {
    try {
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      const ab = await ac.decodeAudioData(buf.slice(0));
      const x = ab.getChannelData(0), sr = ab.sampleRate, hop = Math.floor(sr * STEP);
      const out = [];
      for (let i = 0; i + hop <= Math.min(x.length, sr * maxSec); i += hop) {
        let s = 0;
        for (let k = i; k < i + hop; k++) s += x[k] * x[k];
        out.push(20 * Math.log10(Math.sqrt(s / hop) + 1e-6));
      }
      ac.close();
      return out;
    } catch (_) { return []; }
  }

  function runs(mask, maxGap = 1) {
    const out = []; let start = null, last = null;
    mask.forEach((m, i) => {
      if (!m) return;
      if (start === null) start = i;
      else if (i - last - 1 > maxGap) { out.push([start, last]); start = i; }
      last = i;
    });
    if (start !== null) out.push([start, last]);
    return out;
  }

  const ONSET_DB = 12, MIN_SOUND_DB = 6;
  function splitOnsets(rs, x) {
    // a new sound starts where the level jumps by ONSET_DB or more (a whisper, then knocks)
    const out = [];
    for (const [a, b] of rs) {
      let start = a;
      for (let i = a + 1; i <= b; i++) if (x[i] - x[i - 1] >= ONSET_DB) { out.push([start, i - 1]); start = i; }
      out.push([start, b]);
    }
    return out;
  }

  function detect(rows, levels, zThr = 4) {
    if (rows.length < 8) return [];
    const t = rows.map((r) => r.t), bright = rows.map((r) => r.brightness);
    const dbright = bright.map((b, i) => Math.abs(b - (i ? bright[i - 1] : b)));
    const motion = rows.map((r) => r.motion);
    const signals = [["light_change", dbright, 0.03], ["motion", motion, 0.012]];
    if (levels.length) signals.push(["audio", rows.map((_, i) => levels[Math.min(i, levels.length - 1)]), null]);
    const ev = [];
    let lightMask = null;
    for (const [kind, x, floor] of signals) {
      const z = robustZ(x);
      const med = median(x);
      let mask = z.map((v, i) => v > zThr && (floor == null || x[i] > floor) && (kind !== "audio" || x[i] - med >= MIN_SOUND_DB));
      if (kind === "light_change") lightMask = mask.slice();
      // when the light changes, every pixel changes: that is not movement
      else if (kind === "motion" && lightMask) mask = mask.map((m, i) => m && !(lightMask[i] || lightMask[i - 1] || lightMask[i + 1]));
      let rs = runs(mask, kind === "audio" ? 0 : 1);
      if (kind === "audio") rs = splitOnsets(rs, x);
      for (const [a, b] of rs) {
        let peak = a;
        for (let i = a; i <= b; i++) if (z[i] > z[peak]) peak = i;
        const e = { type: kind, start: t[a], end: t[b] + STEP, confidence: Math.round(Math.min(1, z[peak] / 8) * 100) / 100 };
        if (kind === "light_change") {
          const p0 = bright[Math.max(peak - 1, 0)], delta = (bright[peak] - p0) / Math.max(p0, 1e-3);
          e.description = `the light ${delta > 0 ? "rose" : "dipped"} ${Math.abs(delta * 100).toFixed(0)}% in a quarter second`;
        } else if (kind === "motion") {
          const cxs = rows.slice(a, b + 1).map((r) => r.cx).filter((v) => v != null);
          e.where = whereOf(cxs.length ? median(cxs) : null) || "center";
          e.description = `movement on the ${e.where} side (${(Math.max(...rows.slice(a, b + 1).map((r) => r.area)) * 100).toFixed(0)}% of the frame changed)`;
        } else {
          e.description = `a sound ${(x[peak] - median(x)).toFixed(0)} dB above the room`;
        }
        ev.push(e);
      }
    }
    ev.sort((p, q) => p.start - q.start);
    ev.forEach((e, i) => { e.id = `ev-${String(i + 1).padStart(3, "0")}`; });
    return ev;
  }

  // ------------------------------------------------------------ Dr. Bigotes's natural explanations
  function bigotes(e, all = []) {
    if (e.type === "light_change") return "Hmph. A light that dips and comes back in under a second: a tired bulb, a dimmer, a car's headlights, or the camera's own auto-exposure.";
    if (e.type === "audio") {
      const db = Number((/(\d+) dB/.exec(e.description || "") || [])[1] || 0);
      if (all.some((o) => o.type === "light_change" && Math.abs(o.start - e.start) <= 0.25)) return "It came with the flicker. A failing bulb buzzes when it struggles. Cheap bulbs, not spirits.";
      if (db && db < 20) return "Soft, and not for long: the fridge, the heating ticking, a phone buzzing in a pocket. I would not call it a voice.";
      if (db >= 30) return "Loud and sharp: a door down the hall, the pipes knocking, a neighbour. Ghosts are rarely this loud.";
      return "A sound above the room: a door, the pipes, a neighbour, or the building settling.";
    }
    if (e.type === "motion") return `Movement on the ${e.where || "screen"}: a person, a pet, a coat in a draft, or the camera adjusting. I would check who was home.`;
    if (e.type === "speech") return "Words Whisper was not sure about: someone off camera, a TV, or noise that only looks like words.";
    return "Interesting. Not supernatural, but interesting.";
  }

  // ------------------------------------------------------------ the board (shared with the house)
  function boardBlock(id) {
    return `<div class="board" id="${id}">${WH.boardSVG()}${WH.GLASS}</div>`;
  }
  // opts.slow is the finale: one letter at a time. WH.stage (seance.js) wraps the scene around the board.
  async function spell(boardEl, seq, outEl, opts = {}) {
    const glass = $(".glass", boardEl), slow = !!opts.slow, st = WH.stage;
    outEl.textContent = "";
    boardEl.classList.toggle("slow", slow);
    WH.placeGlass(glass, "REST");
    await sleep(slow ? 900 : 400);
    for (const ch of seq) {
      if (ch === "SPACE") { WH.placeGlass(glass, "REST"); outEl.append(" "); await sleep(slow ? 1100 : 450); continue; }
      WH.placeGlass(glass, ch);
      st && st.glass(boardEl, ch, slow);
      await sleep(slow ? 1500 : 600);
      outEl.insertAdjacentHTML("beforeend", `<span class="lt">${esc(ch)}</span>`);
      st && st.letter(boardEl, ch, slow);
      await sleep(slow ? 450 : 160);
    }
    boardEl.classList.remove("slow");
  }

  // ------------------------------------------------------------ séance UI (one per case kind)
  function seanceUI(prefix) {
    return `<div class="seance" id="${prefix}-seance" hidden>
      <div class="spirit-card" id="${prefix}-spirit"></div>
      ${boardBlock(`${prefix}-board`)}
      <div class="spelled" id="${prefix}-spelled" aria-live="polite"></div>
      <p class="spoken" id="${prefix}-spoken"></p>
      <form class="askspirit" id="${prefix}-ask"><input maxlength="200" placeholder="Ask the spirit..." aria-label="Question for the spirit"><button type="submit">Ask</button></form>
      <div class="suggest" id="${prefix}-suggest"></div>
      <ol class="turns" id="${prefix}-turns"></ol>
      <p class="fiction">Fiction on purpose. The evidence above is real and measured; the spirit, its name and its words are made up by ${"<span class=\"by\"></span>"} from that evidence. No message here is a real communication.</p>
    </div>`;
  }

  const sessions = {};

  async function summon(prefix, investigation, evidence, context = "") {
    const r = await WH.getJSON("/api/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ investigation, evidence, context: context.slice(0, 200) }) });
    sessions[prefix] = r;
    const sp = r.spirit;
    $(`#${prefix}-spirit`).innerHTML = `<div class="arch">${esc(sp.title)}</div><h4>${esc(sp.name)}</h4><p>${esc(sp.backstory)}</p><p class="goal">Its goal: ${esc(sp.goal)}</p>`;
    $(`#${prefix}-seance .by`).textContent = r.model;
    $(`#${prefix}-seance`).hidden = false;
    const qs = ["Is someone here?", "Who are you?", "What were you trying to say?", "Where?", "Why?", "Goodbye"];
    $(`#${prefix}-suggest`).innerHTML = qs.map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join("");
    $(`#${prefix}-suggest`).querySelectorAll("button").forEach((b) => b.addEventListener("click", () =>
      ask(prefix, b.textContent, prefix === "rm" ? afterRoomAnswer : undefined)));
    WH.stage && WH.stage.live(prefix);
    return r;
  }

  async function ask(prefix, question, afterSpell) {
    const s = sessions[prefix];
    if (!s) return;
    const form = $(`#${prefix}-ask`);
    form.querySelector("button").disabled = true;
    $(`#${prefix}-spoken`).textContent = "The glass trembles...";
    const asked = WH.stage && WH.stage.ask(prefix, question);
    try {
      const r = await WH.getJSON(`/api/sessions/${s.session_id}/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
      await asked;
      const msg = r.response.message;
      await showTurn(prefix, r, undefined, { climax: prefix === "uh" && msg === "I AM HERE", finale: prefix === "uh" && msg === "GOODBYE" });
      afterSpell && afterSpell(r);
    } catch (e) {
      $(`#${prefix}-spoken`).textContent = e.message;
    } finally {
      form.querySelector("button").disabled = false;
    }
  }

  // opts.climax: the board spells slowly with the Guardian's voice under it. opts.finale: the session ends.
  async function showTurn(prefix, r, audioUrl, opts = {}) {
    const st = WH.stage;
    $(`#${prefix}-spoken`).textContent = "";
    const audio = audioUrl && !st ? new Audio(audioUrl) : null;
    st && await st.begin(prefix, r, { ...opts, audioUrl });
    await spell($(`#${prefix}-board`), r.response.animation_sequence, $(`#${prefix}-spelled`), { slow: !!opts.climax });
    $(`#${prefix}-spoken`).textContent = r.response.spoken ? `Luna reads the glass: "${r.response.spoken}"` : "";
    if (audio) { try { await audio.play(); } catch (_) { /* autoplay blocked */ } }
    st && await st.read(prefix, r, opts);
    const ids = r.grounding.related_evidence_ids;
    $(`#${prefix}-turns`).insertAdjacentHTML("beforeend", `<li><b>${esc(r.question)}</b> → <span class="msg">${esc(r.response.message)}</span>${r.response.spoken ? ` <i>"${esc(r.response.spoken)}"</i>` : ""} ${ids.map((i) => `<button class="cite" data-ev="${esc(i)}">${esc(i)}</button>`).join("")} <span class="ci">${esc(r.response.by)}</span></li>`);
    ids.forEach((i) => WH.highlight(i, true));
    setTimeout(() => ids.forEach((i) => WH.highlight(i, false)), 2500);
    st && await st.end(prefix, r, opts);
  }

  // skipping ahead: add the turn to the list without the show
  function quickTurn(prefix, r) {
    const ids = r.grounding.related_evidence_ids;
    $(`#${prefix}-spelled`).textContent = r.response.message;
    $(`#${prefix}-turns`).insertAdjacentHTML("beforeend", `<li><b>${esc(r.question)}</b> → <span class="msg">${esc(r.response.message)}</span>${r.response.spoken ? ` <i>"${esc(r.response.spoken)}"</i>` : ""} ${ids.map((i) => `<button class="cite" data-ev="${esc(i)}">${esc(i)}</button>`).join("")} <span class="ci">${esc(r.response.by)}</span></li>`);
  }

  // ------------------------------------------------------------ The Unheard
  let unheard = { evidence: [], series: null, caseData: null, file: null };

  function drawTimeline(series, evidence, duration) {
    const c = $("#uh-timeline"), ctx = c.getContext("2d");
    const w = c.width = c.clientWidth * devicePixelRatio, h = c.height = 120 * devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    const x = (t) => (t / duration) * w;
    for (const e of evidence) {
      ctx.fillStyle = { light_change: "rgba(255,191,60,.25)", audio: "rgba(167,123,255,.28)", motion: "rgba(141,255,207,.22)", speech: "rgba(232,63,139,.25)" }[e.type] || "rgba(255,255,255,.2)";
      ctx.fillRect(x(e.start), 0, Math.max(3, x(e.end) - x(e.start)), h);
    }
    const line = (vals, color) => {
      if (!vals || !vals.length) return;
      const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
      ctx.strokeStyle = color; ctx.lineWidth = 1.5 * devicePixelRatio; ctx.beginPath();
      vals.forEach((v, i) => { const px = x(series.t[i] ?? i * STEP), py = h - 6 - ((v - lo) / span) * (h - 12); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
      ctx.stroke();
    };
    line(series.brightness, "#ffbf3c"); line(series.motion, "#8dffcf"); line(series.audio_db, "#a77bff");
  }

  function renderEvidence(evidence) {
    const box = $("#uh-evidence");
    if (!evidence.length) {
      box.innerHTML = '<p class="notice">Nothing in this recording stands out from itself. No evidence, so no spirit will be invented: the board can only answer NO.</p>';
      return;
    }
    box.innerHTML = evidence.map((e) => `<div class="event" data-ev="${esc(e.id)}" id="ev-${esc(e.id)}">
        <div class="top"><span><span class="id">${esc(e.id)}</span> <button class="ts" data-t="${esc(e.start)}">${esc(e.start.toFixed(2))}s</button> <span class="what">${esc(e.type.replace("_", " "))}</span></span><span class="ci">confidence ${esc(Math.round(e.confidence * 100))}%</span></div>
        <div class="nums">${esc(e.description)}</div>
        <div class="bigotes">🔦 ${esc(bigotes(e, evidence))}</div>
      </div>`).join("");
    box.querySelectorAll(".ts").forEach((b) => b.addEventListener("click", () => { const v = $("#uh-video"); v.currentTime = Number(b.dataset.t); v.play(); }));
  }

  const sameEvidence = (a, b) => JSON.stringify(a.map((e) => [e.type, e.start])) === JSON.stringify(b.map((e) => [e.type, e.start]));

  async function investigate(src, buf, title, measured) {
    const v = $("#uh-video");
    $("#uh-status").textContent = "PARANORMAL.exe is reading the recording, frame by frame, in your browser...";
    v.src = src;
    await new Promise((r, fail) => {
      v.addEventListener("loadedmetadata", r, { once: true });
      v.addEventListener("error", () => fail(new Error("This browser cannot open that video file. Try an MP4 or WebM recording.")), { once: true });
    });
    const rows = await frameFeatures(v, 90, (p) => { $("#uh-status").textContent = `Reading frames... ${Math.round(p * 100)}%`; });
    const levels = await audioLevels(buf, 90);
    // a tab in the background does not paint video frames: every frame comes back the same
    const blind = rows.length > 8 && rows.slice(1).every((r) => r.motion === 0);
    let evidence = detect(rows, levels);
    let series = { t: rows.map((r) => r.t), brightness: rows.map((r) => r.brightness), motion: rows.map((r) => r.motion), audio_db: levels.slice(0, rows.length) };
    let note = `${evidence.length} moment${evidence.length === 1 ? "" : "s"} stand out from the rest of the recording.`;
    if (blind && measured && measured.series) {
      evidence = measured.evidence; series = measured.series;
      note = `this tab was in the background, so the browser could not see the frames. Showing what the pipeline measured on the same clip with OpenCV: ${evidence.length} moments.`;
    } else if (blind) {
      note = "keep this tab in front while it reads the recording (a background tab does not paint video frames). Only the sound could be measured: " + note;
    }
    unheard = { ...unheard, evidence, series, title };
    $("#uh-status").textContent = `${title}: ${note}`;
    v.currentTime = 0;
    drawTimeline(series, evidence, series.t.length * STEP);
    renderEvidence(evidence);
    $("#uh-open").hidden = false;
    return evidence;
  }

  async function openDemo() {
    $("#uh-status").textContent = "Opening the case file...";
    const c = await WH.getJSON("/api/demo/cases");
    const demo = (c.cases || []).find((k) => k.id === "the-warning");
    if (!demo) { $("#uh-status").textContent = "The demo recording is not here yet."; return; }
    unheard.caseData = demo;
    $("#uh-story").innerHTML = `<p>${esc(demo.story)}</p>`;
    if (demo.seance && demo.seance.context) $("#uh-words").value = demo.seance.context;
    const buf = await fetch(demo.video).then((r) => r.arrayBuffer());
    try {
      await investigate(demo.video, buf, "The Warning (a staged recording)", demo);
    } catch (e) { $("#uh-status").textContent = e.message; return; }
    $("#uh-replay").hidden = !demo.seance;
  }

  async function replaySeance() {
    const demo = unheard.caseData;
    if (!demo || !demo.seance) return;
    if (demo.evidence && !sameEvidence(unheard.evidence || [], demo.evidence)) {
      // the recorded séance cites the pipeline's evidence ids: show that list so every citation points somewhere real
      unheard.evidence = demo.evidence;
      renderEvidence(demo.evidence);
      $("#uh-status").textContent += " The recorded séance below used the pipeline's measurements (OpenCV), shown here.";
    }
    $("#uh-seance").hidden = false;
    const sp = demo.seance.spirit;
    $("#uh-spirit").innerHTML = `<div class="arch">${esc(sp.title)}</div><h4>${esc(sp.name)}</h4><p>${esc(sp.backstory)}</p><p class="goal">Its goal: ${esc(sp.goal)}</p>`;
    $("#uh-seance .by").textContent = `${demo.seance.model} (recorded séance)`;
    $("#uh-turns").innerHTML = "";
    const turns = demo.seance.turns, climaxAt = turns.findIndex((t) => t.response.message === "I AM HERE"), st = WH.stage;
    st && st.open("uh");
    for (const [i, turn] of turns.entries()) {
      const climax = i === climaxAt, finale = i === turns.length - 1 && turn.response.message === "GOODBYE";
      if (st && st.skipping("uh") && i < climaxAt) { quickTurn("uh", turn); continue; }
      if (!finale) {
        $("#uh-spoken").textContent = `Luna asks: "${turn.question}"`;
        if (st) await st.ask("uh", turn.question); else await sleep(1600);
      }
      await showTurn("uh", turn, (demo.seance.audio || {})[i], { climax, finale });
      if (st && st.cancelled("uh")) break;
      await sleep(climax ? 600 : st ? 500 : 2200);
    }
    st && st.close("uh");
  }

  function dossier() {
    const s = sessions.uh, demo = unheard.caseData;
    const turns = [...$("#uh-turns").querySelectorAll("li")].map((li) => li.textContent.trim());
    const spirit = s ? s.spirit : demo && demo.seance ? demo.seance.spirit : null;
    const ev = unheard.evidence;
    const html = `<!doctype html><meta charset="utf-8"><title>Case dossier: ${esc(unheard.title || "a recording")}</title>
<style>body{font:15px/1.6 Georgia,serif;max-width:760px;margin:40px auto;padding:0 16px;color:#1b1430}h1{font-family:Impact,sans-serif;letter-spacing:1px}h2{border-bottom:2px solid #1b1430}.f{background:#fbf3e4;border:2px dashed #e83f8b;padding:10px 14px}</style>
<h1>WITCHING HOUR · CASE DOSSIER</h1><p><b>${esc(unheard.title || "A recording")}</b>, investigated with PARANORMAL.exe. Written down by Xochi, the Night Watch.</p>
<h2>1. What the recording really contains</h2><ol>${ev.map((e) => `<li>${esc(e.start.toFixed(2))}s: ${esc(e.type.replace("_", " "))}, ${esc(e.description)} (confidence ${Math.round(e.confidence * 100)}%)</li>`).join("") || "<li>Nothing stood out from the rest of the recording.</li>"}</ol>
<h2>2. What Dr. Bigotes thinks</h2><ul>${ev.map((e) => `<li>${esc(e.id)}: ${esc(bigotes(e, ev))}</li>`).join("")}</ul>
<h2>3. What the board said (fiction)</h2><div class="f">${spirit ? `<p><b>${esc(spirit.name)}</b>, ${esc(spirit.title)}. ${esc(spirit.backstory)}</p>` : ""}<ol>${turns.map((t) => `<li>${esc(t)}</li>`).join("") || "<li>No séance yet.</li>"}</ol><p>The spirit and its words were made up by an open model from the evidence in section 1. They are not a real message.</p></div>
<h2>4. Xochi's note</h2><p>I carried the message across, the way xolos do. Whether you believe it is up to you. What the camera really caught is in section 1, and that part is true.</p>`;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    a.download = "witching-hour-dossier.html";
    a.click();
  }

  // ------------------------------------------------------------ The Room (live)
  let room = { stream: null, timer: null, evidence: [], prev: null, hist: { motion: [], db: [], dbright: [] }, lastB: null, watchUntil: 0 };

  function liveEvent(kind, description, z, extra = {}) {
    const n = room.evidence.length + 1;
    const e = { id: `live-${String(n).padStart(3, "0")}`, type: kind, start: Math.round((performance.now() - room.t0) / 100) / 10, confidence: Math.round(Math.min(1, z / 8) * 100) / 100, description, ...extra };
    e.end = e.start + STEP;
    room.evidence.push(e);
    $("#rm-log").insertAdjacentHTML("afterbegin", `<li data-ev="${esc(e.id)}"><span class="id">${esc(e.id)}</span> ${esc(e.start.toFixed(1))}s · ${esc(description)} <span class="ci">${Math.round(e.confidence * 100)}%</span></li>`);
    if (kind === "motion" && performance.now() < room.watchUntil) haunt();
    const s = sessions.rm;
    if (s) WH.getJSON(`/api/sessions/${s.session_id}/evidence`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ evidence: [e] }) }).catch(() => {});
  }

  // The Room works without a camera too: simulated moments, so anyone can play the last act.
  const ROOM_DEMO = [
    { id: "live-001", type: "light_change", start: 1.2, confidence: 0.92, description: "the light changed suddenly (simulated for the demo)" },
    { id: "live-002", type: "audio", start: 3.5, confidence: 0.88, description: "a sound 24 dB above the room (simulated for the demo)" },
    { id: "live-003", type: "motion", start: 5.0, confidence: 0.81, where: "left", description: "movement on the left side (simulated for the demo)" },
  ];
  function afterRoomAnswer() {
    room.watchUntil = performance.now() + 6000;
    if (room.demo && WH.stage) WH.stage.roomScare("rm");
  }
  async function roomDemo() {
    room.demo = true;
    room.evidence = ROOM_DEMO.map((e) => ({ ...e, end: e.start + STEP }));
    $("#rm-log").innerHTML = room.evidence.map((e) => `<li data-ev="${esc(e.id)}"><span class="id">${esc(e.id)}</span> ${esc(e.start.toFixed(1))}s · ${esc(e.description)} <span class="ci">${Math.round(e.confidence * 100)}%</span></li>`).join("");
    $("#rm-status").textContent = "Demo room, no camera: the three moments below are simulated. Ask the board, then watch what happens when the glass stops.";
    $("#rm-meters").textContent = "";
    await summon("rm", "the room (demo)", room.evidence);
    WH.stage && WH.stage.roomIntro("rm");
  }

  function haunt() {
    room.watchUntil = 0;
    const o = $("#rm-haunt");
    o.hidden = false;
    setTimeout(() => { o.hidden = true; }, 2600);
  }

  async function startRoom() {
    room.demo = false;
    try {
      room.stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 180 }, audio: true });
    } catch (e) {
      $("#rm-status").textContent = "No camera or microphone permission. The Room needs both, and they never leave this page.";
      return;
    }
    const v = $("#rm-video");
    v.srcObject = room.stream;
    await v.play();
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const an = ac.createAnalyser();
    an.fftSize = 2048;
    ac.createMediaStreamSource(room.stream).connect(an);
    const buf = new Float32Array(an.fftSize);
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const ctx = c.getContext("2d", { willReadFrequently: true });
    room.t0 = performance.now();
    room.ac = ac;
    $("#rm-status").textContent = "Listening. Stay still for a few seconds so PARANORMAL.exe learns what your room is like.";
    const cool = { motion: 0, audio: 0, light: 0 };
    room.timer = setInterval(() => {
      ctx.drawImage(v, 0, 0, W, H);
      const [row, g] = frameStats(ctx, room.prev);
      room.prev = g;
      an.getFloatTimeDomainData(buf);
      let s = 0; for (const x of buf) s += x * x;
      const db = 20 * Math.log10(Math.sqrt(s / buf.length) + 1e-6);
      const db_ = room.lastB == null ? 0 : Math.abs(row.brightness - room.lastB);
      room.lastB = row.brightness;
      const h = room.hist;
      h.motion.push(row.motion); h.db.push(db); h.dbright.push(db_);
      for (const k of Object.keys(h)) if (h[k].length > 120) h[k].shift();
      $("#rm-meters").innerHTML = `light ${(row.brightness * 100).toFixed(0)}% · motion ${(row.motion * 1000).toFixed(1)} · sound ${db.toFixed(0)} dB`;
      if (h.motion.length < 20) return;
      const now = performance.now();
      const zLast = (arr) => { const z = robustZ(arr); return z[z.length - 1]; };
      const zm = zLast(h.motion), za = zLast(h.db), zl = zLast(h.dbright);
      if (zm > 5 && row.motion > 0.012 && now > cool.motion) { cool.motion = now + 2500; liveEvent("motion", `movement on the ${whereOf(row.cx) || "center"} side`, zm, { where: whereOf(row.cx) || "center" }); }
      if (za > 5 && now > cool.audio) { cool.audio = now + 2500; liveEvent("audio", `a sound ${(db - median(h.db)).toFixed(0)} dB above the room`, za); }
      if (zl > 6 && db_ > 0.03 && now > cool.light) { cool.light = now + 2500; liveEvent("light_change", "the light changed suddenly", zl); }
    }, STEP * 1000);
    $("#rm-start").textContent = "Stop";
    $("#rm-seance-open").hidden = false;
  }

  function stopRoom() {
    clearInterval(room.timer);
    room.stream && room.stream.getTracks().forEach((t) => t.stop());
    room.ac && room.ac.close();
    room = { stream: null, timer: null, evidence: room.evidence, prev: null, hist: { motion: [], db: [], dbright: [] }, lastB: null, watchUntil: 0 };
    $("#rm-start").textContent = "Turn on camera and microphone";
    $("#rm-status").textContent = "Stopped. Nothing was recorded.";
  }

  // ------------------------------------------------------------ boot
  function boot() {
    $("#uh-seance-slot").innerHTML = seanceUI("uh");
    $("#rm-seance-slot").innerHTML = seanceUI("rm");
    $("#uh-demo").addEventListener("click", openDemo);
    $("#uh-file").addEventListener("change", async (ev) => {
      const f = ev.target.files[0];
      if (!f) return;
      unheard.caseData = null;
      $("#uh-replay").hidden = true;
      $("#uh-story").innerHTML = "<p>Your recording. It stays in this browser: only the list of moments below is ever sent to the board.</p>";
      try {
        await investigate(URL.createObjectURL(f), await f.arrayBuffer(), f.name);
      } catch (e) { $("#uh-status").textContent = e.message; }
    });
    $("#uh-open").addEventListener("click", async () => { await summon("uh", unheard.title || "recording", unheard.evidence, $("#uh-words").value.trim()); $("#uh-seance").scrollIntoView({ behavior: "smooth", block: "center" }); });
    $("#uh-replay").addEventListener("click", replaySeance);
    $("#uh-dossier").addEventListener("click", dossier);
    $("#uh-ask").addEventListener("submit", (e) => { e.preventDefault(); const i = $("input", e.target); if (i.value.trim()) { ask("uh", i.value.trim()); i.value = ""; } });
    $("#rm-start").addEventListener("click", () => (room.stream ? stopRoom() : startRoom()));
    $("#rm-seance-open").addEventListener("click", () => summon("rm", "the room", room.evidence));
    $("#rm-ask").addEventListener("submit", (e) => {
      e.preventDefault();
      const i = $("input", e.target);
      if (!i.value.trim()) return;
      ask("rm", i.value.trim(), afterRoomAnswer);
      i.value = "";
    });
  }
  WH.bigotes = bigotes;
  WH.roomDemo = roomDemo;
  WH.haunt = haunt;
  WH.evidenceFor = (prefix) => (prefix === "rm" ? room.evidence : unheard.evidence) || [];
  boot();
})();
