// PARANORMAL.exe: the crew's terminal for The Unheard (a recording) and The Room (live).
// The recording and the camera never leave this page: the browser measures light, motion and
// sound. Summoning sends event summaries, optional memory text and questions to the app server.
(() => {
  "use strict";
  const WH = window.WH;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = WH.esc;
  const STEP = 0.25, W = 160, H = 90;
  const MAX_FILE_BYTES = 24 * 1024 * 1024, MAX_SECONDS = 90;
  const sleep = (ms) => new Promise((r) => setTimeout(r, WH.reduceMotion ? 0 : ms));
  const cancelled = () => new DOMException("Cancelled", "AbortError");
  function checkAbort(signal) { if (signal && signal.aborted) throw cancelled(); }
  function mediaEvent(video, event, setup, signal, ready) {
    checkAbort(signal);
    return new Promise((resolve, reject) => {
      let timer;
      const finish = (error) => {
        clearTimeout(timer);
        video.removeEventListener(event, done);
        video.removeEventListener("error", failed);
        signal && signal.removeEventListener("abort", aborted);
        error ? reject(error) : resolve();
      };
      const done = () => finish();
      const failed = () => finish(new Error("This browser cannot read that video. Try MP4 or WebM."));
      const aborted = () => finish(cancelled());
      video.addEventListener(event, done, { once: true });
      video.addEventListener("error", failed, { once: true });
      signal && signal.addEventListener("abort", aborted, { once: true });
      timer = setTimeout(() => finish(new Error("The video did not become ready. Try a shorter recording.")), 10000);
      try { setup && setup(); if (ready && ready()) finish(); } catch (error) { finish(error); }
    });
  }

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

  async function frameFeatures(video, maxSec, onProgress, signal) {
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const ctx = c.getContext("2d", { willReadFrequently: true });
    const dur = Math.min(video.duration, maxSec), rows = [];
    let prev = null;
    for (let t = 0; t < dur; t += STEP) {
      checkAbort(signal);
      if (document.hidden) throw new Error("Keep this tab visible while it measures the recording.");
      // A still frame is valid evidence. Never treat a quiet opening as a frozen decoder.
      await mediaEvent(video, "seeked", () => { video.currentTime = t; }, signal,
        () => !video.seeking && Math.abs(video.currentTime - t) < 0.001 && video.readyState >= 2);
      checkAbort(signal);
      ctx.drawImage(video, 0, 0, W, H);
      const [row, g] = frameStats(ctx, prev);
      row.t = Math.round(t * 100) / 100;
      rows.push(row); prev = g;
      onProgress && onProgress(t / dur);
    }
    return rows;
  }

  async function audioLevels(buf, maxSec, signal) {
    let ac;
    const close = () => { if (ac && ac.state !== "closed") ac.close().catch(() => {}); };
    try {
      checkAbort(signal);
      ac = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      signal && signal.addEventListener("abort", close, { once: true });
      const ab = await ac.decodeAudioData(buf);
      checkAbort(signal);
      const x = ab.getChannelData(0), sr = ab.sampleRate, hop = Math.floor(sr * STEP), out = [];
      for (let i = 0; i + hop <= Math.min(x.length, sr * maxSec); i += hop) {
        let s = 0;
        for (let k = i; k < i + hop; k++) s += x[k] * x[k];
        out.push(20 * Math.log10(Math.sqrt(s / hop) + 1e-6));
      }
      return out;
    } catch (error) {
      checkAbort(signal);
      return []; // The result explicitly says that audio was not measured.
    } finally {
      signal && signal.removeEventListener("abort", close);
      close();
    }
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
  async function spell(boardEl, seq, outEl, active) {
    const glass = $(".glass", boardEl);
    outEl.textContent = "";
    WH.placeGlass(glass, "REST");
    await sleep(500);
    for (const ch of seq) {
      if (!active()) return false;
      if (ch === "SPACE") {
        WH.placeGlass(glass, "REST"); outEl.textContent += " "; await sleep(650); continue;
      }
      WH.placeGlass(glass, ch);
      await sleep(850);
      if (!active()) return false;
      outEl.textContent += ch;
      await sleep(220);
    }
    return active();
  }

  function seanceUI(prefix) {
    return '<div class="seance" id="' + prefix + '-seance" hidden>' +
      '<div class="spirit-card" id="' + prefix + '-spirit"></div>' +
      boardBlock(prefix + "-board") +
      '<div class="spelled" id="' + prefix + '-spelled" aria-live="off"></div>' +
      '<p class="spoken" id="' + prefix + '-spoken" role="status" aria-live="polite" aria-atomic="true"></p>' +
      '<form class="askspirit" id="' + prefix + '-ask"><input maxlength="200" placeholder="Ask the spirit..." aria-label="Question for the spirit"><button type="submit">Ask</button></form>' +
      '<div class="suggest" id="' + prefix + '-suggest"></div>' +
      '<ol class="turns" id="' + prefix + '-turns"></ol>' +
      '<p class="fiction">Fiction on purpose. The spirit and its words are invented; citations identify their inspiration, not proof. Identity source: <span class="by"></span>. Each turn lists its response source. No message here is a real communication.</p></div>';
  }

  const sessions = {};
  const boards = Object.fromEntries(["uh", "rm"].map((prefix) =>
    [prefix, { revision: 0, busy: false, controller: null, audio: null, spirit: null, source: "", mode: "idle" }]));
  const sourceLabel = (source) => source === "template" ? "scripted template" : (source || "source not recorded");
  const boardCurrent = (prefix, revision) => boards[prefix].revision === revision;
  function closeRemote(sid) {
    if (sid) WH.getJSON("/api/sessions/" + encodeURIComponent(sid) + "/close",
      { method: "POST", keepalive: true }).catch(() => {});
  }
  function boardBusy(prefix, busy) {
    boards[prefix].busy = busy;
    $("#" + prefix + "-seance").setAttribute("aria-busy", String(busy));
    $("#" + prefix + "-seance").querySelectorAll("input, button").forEach((el) => { el.disabled = busy; });
    $(prefix === "uh" ? "#uh-open" : "#rm-seance-open").disabled = busy;
    if (prefix === "uh") refreshUnheardControls();
  }
  function resetBoard(prefix) {
    const b = boards[prefix], old = sessions[prefix];
    b.revision++;
    b.controller && b.controller.abort();
    b.controller = null;
    if (b.audio) { b.audio.pause(); b.audio = null; }
    delete sessions[prefix];
    b.spirit = null; b.source = ""; b.mode = "idle";
    $("#" + prefix + "-seance").hidden = true;
    ["spirit", "spelled", "spoken", "turns", "suggest"].forEach((id) => {
      $("#" + prefix + "-" + id).textContent = "";
    });
    $("#" + prefix + "-ask").reset();
    $("#" + prefix + "-ask").hidden = false;
    $("#" + prefix + "-suggest").hidden = false;
    boardBusy(prefix, false);
    old && closeRemote(old.session_id);
  }
  function renderSpirit(prefix, spirit, source) {
    boards[prefix].spirit = spirit;
    boards[prefix].source = source;
    $("#" + prefix + "-spirit").innerHTML = '<div class="arch">' + esc(spirit.title) +
      '</div><h4>' + esc(spirit.name) + '</h4><p>' + esc(spirit.backstory) +
      '</p><p class="goal">Its goal: ' + esc(spirit.goal) + "</p>";
    $("#" + prefix + "-seance .by").textContent = sourceLabel(source);
    $("#" + prefix + "-seance").hidden = false;
  }

  async function summon(prefix, investigation, evidence, context, revision, signal) {
    const r = await WH.getJSON("/api/sessions", { method: "POST", signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ investigation, evidence, context: context.slice(0, 200) }) });
    if (!boardCurrent(prefix, revision)) { closeRemote(r.session_id); return null; }
    sessions[prefix] = r;
    boards[prefix].mode = "live";
    renderSpirit(prefix, r.spirit, r.spirit.by || r.model);
    const qs = ["Is someone here?", "Who are you?", "What were you trying to say?", "Where?", "Why?", "Goodbye"];
    $("#" + prefix + "-suggest").innerHTML = qs.map((q) =>
      '<button type="button" class="chip">' + esc(q) + "</button>").join("");
    $("#" + prefix + "-suggest").querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => ask(prefix, b.textContent,
        prefix === "rm" ? () => { if (room.stream) room.watchUntil = performance.now() + 6000; } : undefined)));
    return r;
  }

  async function openBoard(prefix, investigation, evidence, context = "") {
    if (boards[prefix].busy || (prefix === "uh" && analysisController)) return;
    resetBoard(prefix);
    const b = boards[prefix], revision = b.revision, controller = new AbortController();
    b.controller = controller;
    boardBusy(prefix, true);
    const status = $("#" + prefix + "-status");
    status.textContent = "Opening a fictional spirit session...";
    const timer = setTimeout(() => controller.abort(), 180000);
    try {
      const r = await summon(prefix, investigation, evidence, context, revision, controller.signal);
      if (!r || !boardCurrent(prefix, revision)) return;
      status.textContent = "Fictional session ready. Identity source: " + sourceLabel(r.spirit.by || r.model) + ".";
      $("#" + prefix + "-seance").scrollIntoView({ behavior: WH.reduceMotion ? "auto" : "smooth", block: "center" });
    } catch (error) {
      if (boardCurrent(prefix, revision)) {
        resetBoard(prefix);
        status.textContent = error.name === "AbortError"
          ? "Opening the board timed out. Try again or use the recorded replay."
          : "Could not open the board: " + error.message;
      }
    } finally {
      clearTimeout(timer);
      if (boardCurrent(prefix, revision)) { b.controller = null; boardBusy(prefix, false); }
    }
  }

  async function ask(prefix, question, afterSpell) {
    const s = sessions[prefix], b = boards[prefix];
    if (!s || b.busy || b.mode !== "live") return;
    const revision = b.revision, controller = new AbortController();
    b.controller = controller;
    boardBusy(prefix, true);
    $("#" + prefix + "-spoken").textContent = "The glass trembles...";
    const timer = setTimeout(() => controller.abort(), 180000);
    try {
      const r = await WH.getJSON("/api/sessions/" + encodeURIComponent(s.session_id) + "/ask",
        { method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }) });
      if (!boardCurrent(prefix, revision) || !await showTurn(prefix, r, null, revision)) return;
      if (r.response.message === "GOODBYE") {
        b.mode = "closed"; delete sessions[prefix]; closeRemote(s.session_id);
        $("#" + prefix + "-ask").hidden = true;
        $("#" + prefix + "-suggest").hidden = true;
        $("#" + prefix + "-status").textContent = "The fictional session is closed.";
      } else { afterSpell && afterSpell(r); }
    } catch (error) {
      if (boardCurrent(prefix, revision)) $("#" + prefix + "-spoken").textContent =
        error.name === "AbortError" ? "The answer timed out. Try again." : error.message;
    } finally {
      clearTimeout(timer);
      if (boardCurrent(prefix, revision)) { b.controller = null; boardBusy(prefix, false); }
    }
  }

  async function showTurn(prefix, r, audioUrl, revision) {
    const active = () => boardCurrent(prefix, revision);
    if (!active()) return false;
    $("#" + prefix + "-spoken").textContent = "";
    if (!await spell($("#" + prefix + "-board"), r.response.animation_sequence,
      $("#" + prefix + "-spelled"), active)) return false;
    $("#" + prefix + "-spoken").textContent = r.response.spoken ? '"' + r.response.spoken + '"' : "";
    const b = boards[prefix];
    if (b.audio) { b.audio.pause(); b.audio = null; }
    if (audioUrl) {
      const audio = new Audio(audioUrl);
      b.audio = audio;
      try { await audio.play(); } catch (_) { /* text remains available */ }
      if (!active()) { audio.pause(); return false; }
    }
    const ids = r.grounding.related_evidence_ids;
    $("#" + prefix + "-turns").insertAdjacentHTML("beforeend", "<li><b>" + esc(r.question) +
      '</b> → <span class="msg">' + esc(r.response.message) + "</span>" +
      (r.response.spoken ? ' <i>"' + esc(r.response.spoken) + '"</i>' : "") + " " +
      ids.map((i) => '<button class="cite" data-ev="' + esc(i) + '">' + esc(i) + "</button>").join("") +
      ' <span class="ci">' + esc(sourceLabel(r.response.by)) + "</span></li>");
    ids.forEach((i) => WH.highlight(i, true));
    setTimeout(() => ids.forEach((i) => WH.highlight(i, false)), 2500);
    return true;
  }

  // ------------------------------------------------------------ The Unheard
  let unheard = { evidence: [], series: null, caseData: null, title: "" };
  let analysisController = null, analysisVersion = 0, recordingURL = null;
  function refreshUnheardControls() {
    const busy = !!analysisController || boards.uh.busy;
    ["#uh-demo", "#uh-file", "#uh-open", "#uh-replay"].forEach((id) => { $(id).disabled = busy; });
    $("#uh-dossier").disabled = busy || !unheard.series;
    const label = $("#uh-file").closest("label");
    if (label) { label.tabIndex = busy ? -1 : 0; label.setAttribute("aria-disabled", String(busy)); }
    const cancel = $("#uh-cancel");
    if (cancel) cancel.hidden = !busy && boards.uh.mode !== "live" && boards.uh.mode !== "replay";
  }
  function resetRecording() {
    analysisVersion++;
    analysisController && analysisController.abort();
    analysisController = null;
    resetBoard("uh");
    const video = $("#uh-video");
    video.pause(); video.removeAttribute("src"); video.load();
    if (recordingURL) { URL.revokeObjectURL(recordingURL); recordingURL = null; }
    unheard = { evidence: [], series: null, caseData: null, title: "" };
    $("#uh-open").hidden = true; $("#uh-replay").hidden = true;
    $("#uh-evidence").textContent = ""; $("#uh-story").textContent = ""; $("#uh-words").value = "";
    const canvas = $("#uh-timeline");
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    refreshUnheardControls();
  }
  async function analyze(task) {
    resetRecording();
    const version = analysisVersion, controller = new AbortController();
    analysisController = controller;
    refreshUnheardControls();
    const timer = setTimeout(() => controller.abort(), 180000);
    try { await task(controller.signal); }
    catch (error) {
      if (version === analysisVersion) {
        const message = error.name === "AbortError"
          ? "Analysis cancelled or timed out. Try a shorter recording."
          : error.message;
        resetRecording();
        $("#uh-status").textContent = message;
      }
    } finally {
      clearTimeout(timer);
      if (version === analysisVersion) { analysisController = null; refreshUnheardControls(); }
    }
  }
  function checkFileSize(blob) {
    if (!blob.size || blob.size > MAX_FILE_BYTES) throw new Error("Choose a recording up to 24 MiB and 90 seconds.");
  }
  async function fetchRecording(url, signal) {
    const response = await fetch(url, { signal });
    if (!response.ok) throw new Error("Could not download the demo recording (" + response.status + ").");
    if (Number(response.headers.get("content-length")) > MAX_FILE_BYTES) throw new Error("The demo recording exceeds the 24 MiB limit.");
    if (!response.body) throw new Error("This browser cannot stream the demo safely. Try a local recording.");
    const reader = response.body.getReader(), chunks = [];
    let size = 0, complete = false;
    try {
      while (true) {
        checkAbort(signal);
        const result = await reader.read();
        if (result.done) { complete = true; break; }
        size += result.value.byteLength;
        if (size > MAX_FILE_BYTES) throw new Error("The demo recording exceeds the 24 MiB limit.");
        chunks.push(result.value);
      }
    } finally {
      if (!complete) await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    const blob = new Blob(chunks, { type: response.headers.get("content-type") || "video/mp4" });
    checkFileSize(blob);
    return blob;
  }

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
      box.innerHTML = '<p class="notice">No measured signal crossed the detection threshold. With no evidence, the board uses the silent template.</p>';
      return;
    }
    box.innerHTML = evidence.map((e) => '<div class="event" data-ev="' + esc(e.id) + '" id="ev-' + esc(e.id) + '">' +
      '<div class="top"><span><span class="id">' + esc(e.id) + '</span> <button class="ts" data-t="' + esc(e.start) + '">' +
      esc(e.start.toFixed(2)) + 's</button> <span class="what">' + esc(e.type.replace("_", " ")) +
      '</span></span><span class="ci">relative signal intensity ' + esc(Math.round(e.confidence * 100)) +
      '%</span></div><div class="nums">' + esc(e.description) + '</div><div class="bigotes">🔦 ' +
      esc(bigotes(e, evidence)) + "</div></div>").join("");
    box.querySelectorAll(".ts").forEach((b) => b.addEventListener("click", () => {
      const video = $("#uh-video"); video.currentTime = Number(b.dataset.t);
      video.play().catch(() => { $("#uh-status").textContent = "Press the video's play button to view this moment."; });
    }));
  }

  async function investigate(blob, title, measured, signal) {
    checkFileSize(blob);
    const video = $("#uh-video");
    $("#uh-status").textContent = "Checking the recording before analysis...";
    recordingURL = URL.createObjectURL(blob);
    await mediaEvent(video, "loadedmetadata", () => { video.src = recordingURL; video.load(); }, signal,
      () => video.readyState >= 1);
    if (!Number.isFinite(video.duration) || video.duration <= 0 || video.duration > MAX_SECONDS) {
      throw new Error("Choose a recording no longer than 90 seconds; longer files are not decoded.");
    }
    await mediaEvent(video, "loadeddata", null, signal, () => video.readyState >= 2);
    let evidence, series, note;
    try {
      const rows = await frameFeatures(video, MAX_SECONDS, (p) => {
        $("#uh-status").textContent = "Reading frames... " + Math.round(p * 100) + "%";
      }, signal);
      checkAbort(signal);
      // Size and duration have been checked before allocating or decoding the audio buffer.
      const levels = await audioLevels(await blob.arrayBuffer(), MAX_SECONDS, signal);
      checkAbort(signal);
      evidence = detect(rows, levels);
      series = { t: rows.map((r) => r.t), brightness: rows.map((r) => r.brightness),
        motion: rows.map((r) => r.motion), audio_db: levels.slice(0, rows.length) };
      note = evidence.length + " measured moment(s) crossed the detection threshold." +
        (levels.length ? "" : " No audio was measured; these results only use video.");
    } catch (error) {
      checkAbort(signal);
      if (!measured || !measured.series || !Array.isArray(measured.evidence)) throw error;
      evidence = measured.evidence; series = measured.series;
      note = "Browser analysis could not complete (" + error.message +
        "). Showing the pipeline's recorded measurements of this same staged clip: " + evidence.length + " moments.";
    }
    checkAbort(signal);
    unheard = { ...unheard, evidence, series, title };
    $("#uh-status").textContent = title + ": " + note + " Intensity is a heuristic signal score, not a probability.";
    video.currentTime = 0;
    drawTimeline(series, evidence, series.t.length * STEP);
    renderEvidence(evidence);
    $("#uh-open").hidden = false;
    refreshUnheardControls();
    return evidence;
  }

  async function openDemo() {
    return analyze(async (signal) => {
      $("#uh-status").textContent = "Opening the case file...";
      const result = await WH.getJSON("/api/demo/cases", { signal });
      checkAbort(signal);
      const demo = (result.cases || []).find((item) => item.id === "the-warning");
      if (!demo) throw new Error("The demo recording is not here yet.");
      const blob = await fetchRecording(demo.video, signal);
      checkAbort(signal);
      unheard.caseData = demo;
      $("#uh-story").textContent = demo.story;
      $("#uh-words").value = (demo.seance && demo.seance.context) || "";
      await investigate(blob, "The Warning (a staged recording)", demo, signal);
      $("#uh-replay").hidden = !demo.seance;
    });
  }

  async function replaySeance() {
    const demo = unheard.caseData;
    if (!demo || !demo.seance || analysisController || boards.uh.busy) return;
    if (!Array.isArray(demo.evidence)) { $("#uh-status").textContent = "Recorded evidence is missing; replay is unavailable."; return; }
    resetBoard("uh"); // A replay is never an interactive server session.
    const b = boards.uh, revision = b.revision;
    b.mode = "replay"; boardBusy("uh", true);
    unheard.evidence = demo.evidence;
    if (demo.series) unheard.series = demo.series;
    renderEvidence(unheard.evidence);
    if (unheard.series) drawTimeline(unheard.series, unheard.evidence, unheard.series.t.length * STEP);
    $("#uh-status").textContent = "Recorded fictional séance, using the pipeline's measurements. Cancel to stop the replay.";
    const spirit = demo.seance.spirit;
    renderSpirit("uh", spirit, spirit.by);
    $("#uh-ask").hidden = true; $("#uh-suggest").hidden = true;
    try {
      for (const [i, turn] of demo.seance.turns.entries()) {
        if (!boardCurrent("uh", revision)) return;
        $("#uh-spoken").textContent = 'Luna asks: "' + turn.question + '"';
        await sleep(1600);
        if (!boardCurrent("uh", revision) || !await showTurn("uh", turn, (demo.seance.audio || {})[i], revision)) return;
        await sleep(2200);
      }
      if (boardCurrent("uh", revision)) $("#uh-status").textContent = "Recorded séance complete. Summon a new spirit to ask your own questions.";
    } catch (error) {
      if (boardCurrent("uh", revision)) $("#uh-status").textContent = "Replay stopped: " + error.message;
    } finally {
      if (boardCurrent("uh", revision)) boardBusy("uh", false);
    }
  }

  function dossier() {
    const b = boards.uh, spirit = b.spirit, evidence = unheard.evidence;
    const turns = [...$("#uh-turns").querySelectorAll("li")].map((li) => li.textContent.trim());
    const html = '<!doctype html><meta charset="utf-8"><title>Case dossier: ' + esc(unheard.title || "a recording") + "</title>" +
      '<style>body{font:15px/1.6 Georgia,serif;max-width:760px;margin:40px auto;padding:0 16px;color:#1b1430}h1{font-family:Impact,sans-serif}h2{border-bottom:2px solid #1b1430}.f{background:#fbf3e4;border:2px dashed #e83f8b;padding:10px 14px}</style>' +
      "<h1>WITCHING HOUR · CASE DOSSIER</h1><p><b>" + esc(unheard.title || "A recording") +
      "</b>, investigated with PARANORMAL.exe. Written down by Xochi, the Night Watch.</p>" +
      "<h2>1. Measured signals</h2><ol>" + (evidence.map((e) => "<li>" + esc(e.start.toFixed(2)) +
        "s: " + esc(e.type.replace("_", " ")) + ", " + esc(e.description) + " (relative signal intensity " +
        Math.round(e.confidence * 100) + "%)</li>").join("") || "<li>No signal crossed the detection threshold.</li>") +
      "</ol><p>Intensity is a heuristic score, not a probability or proof of a cause.</p>" +
      "<h2>2. What Dr. Bigotes thinks</h2><ul>" + evidence.map((e) => "<li>" + esc(e.id) + ": " +
        esc(bigotes(e, evidence)) + "</li>").join("") + "</ul><h2>3. What the board said (fiction)</h2><div class=\"f\">" +
      (spirit ? "<p><b>" + esc(spirit.name) + "</b>, " + esc(spirit.title) + ". " + esc(spirit.backstory) +
        "</p><p>Identity source: " + esc(sourceLabel(b.source)) + ".</p>" : "") +
      "<ol>" + (turns.map((turn) => "<li>" + esc(turn) + "</li>").join("") || "<li>No séance yet.</li>") +
      "</ol><p>The spirit and its messages are fiction. Each turn lists its response source; citations identify inspiration, not proof.</p></div>" +
      "<h2>4. Xochi's note</h2><p>The measured signals are in section 1. The crew's explanations and the spirit's story are interpretations.</p>";
    const a = document.createElement("a"), url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    a.href = url; a.download = "witching-hour-dossier.html"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // ------------------------------------------------------------ The Room (live)
  const emptyRoom = () => ({ stream: null, timer: null, ac: null, starting: false, evidence: [],
    nextEvidence: 1, prev: null, hist: { motion: [], db: [], dbright: [] }, lastB: null, watchUntil: 0, hauntTimer: null });
  let room = emptyRoom(), roomRevision = 0;

  function liveEvent(kind, description, z, extra = {}) {
    const e = { id: "live-" + String(room.nextEvidence++).padStart(3, "0"), type: kind,
      start: Math.round((performance.now() - room.t0) / 100) / 10,
      confidence: Math.round(Math.min(1, z / 8) * 100) / 100, description, ...extra };
    e.end = e.start + STEP;
    room.evidence.push(e);
    room.evidence = room.evidence.slice(-40);
    $("#rm-log").insertAdjacentHTML("afterbegin", '<li data-ev="' + esc(e.id) + '"><span class="id">' +
      esc(e.id) + "</span> " + esc(e.start.toFixed(1)) + "s · " + esc(description) +
      ' <span class="ci">relative intensity ' + Math.round(e.confidence * 100) + "%</span></li>");
    while ($("#rm-log").children.length > 40) $("#rm-log").lastElementChild.remove();
    if (kind === "motion" && performance.now() < room.watchUntil) haunt();
    const session = sessions.rm;
    if (session) WH.getJSON("/api/sessions/" + encodeURIComponent(session.session_id) + "/evidence",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ evidence: [e] }) })
      .catch(() => {
        if (sessions.rm && sessions.rm.session_id === session.session_id) {
          resetBoard("rm");
          $("#rm-status").textContent = "The board could not receive new evidence. Capture is still local; summon a new session to continue.";
        }
      });
  }

  function haunt() {
    room.watchUntil = 0;
    clearTimeout(room.hauntTimer);
    $("#rm-haunt").hidden = false;
    room.hauntTimer = setTimeout(() => { $("#rm-haunt").hidden = true; }, 2600);
  }

  async function startRoom() {
    if (room.starting || room.stream) return;
    stopRoom("");
    const revision = ++roomRevision, current = room;
    current.starting = true;
    $("#rm-start").textContent = "Cancel camera startup";
    $("#rm-status").textContent = "Waiting for camera and microphone permission...";
    let acquired = null;
    try {
      acquired = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 180 }, audio: true });
      if (revision !== roomRevision) { acquired.getTracks().forEach((track) => track.stop()); return; }
      current.stream = acquired;
      const video = $("#rm-video");
      video.srcObject = acquired;
      await video.play();
      if (revision !== roomRevision) return;
      current.ac = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      if (current.ac.state === "suspended") await current.ac.resume();
      if (revision !== roomRevision) return;
      const analyser = current.ac.createAnalyser();
      analyser.fftSize = 2048;
      current.ac.createMediaStreamSource(acquired).connect(analyser);
      const buffer = new Float32Array(analyser.fftSize);
      const canvas = document.createElement("canvas"); canvas.width = W; canvas.height = H;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      current.t0 = performance.now();
      $("#rm-status").textContent = "Listening locally. Stay still for five seconds to establish a baseline. Intensity is a relative signal score, not a probability.";
      const cool = { motion: 0, audio: 0, light: 0 };
      current.timer = setInterval(() => {
        if (revision !== roomRevision) return;
        try {
          ctx.drawImage(video, 0, 0, W, H);
          const [row, g] = frameStats(ctx, current.prev);
          current.prev = g;
          analyser.getFloatTimeDomainData(buffer);
          let sum = 0; for (const x of buffer) sum += x * x;
          const db = 20 * Math.log10(Math.sqrt(sum / buffer.length) + 1e-6);
          const dbright = current.lastB == null ? 0 : Math.abs(row.brightness - current.lastB);
          current.lastB = row.brightness;
          const history = current.hist;
          history.motion.push(row.motion); history.db.push(db); history.dbright.push(dbright);
          for (const key of Object.keys(history)) if (history[key].length > 120) history[key].shift();
          $("#rm-meters").textContent = "light " + (row.brightness * 100).toFixed(0) + "% · motion " +
            (row.motion * 1000).toFixed(1) + " · sound " + db.toFixed(0) + " dB";
          if (history.motion.length < 20) return;
          const now = performance.now(), lastZ = (values) => { const z = robustZ(values); return z[z.length - 1]; };
          const zm = lastZ(history.motion), za = lastZ(history.db), zl = lastZ(history.dbright);
          const lightChange = zl > 6 && dbright > 0.03;
          if (!lightChange && zm > 5 && row.motion > 0.012 && now > cool.motion) {
            cool.motion = now + 2500;
            liveEvent("motion", "movement on the " + (whereOf(row.cx) || "center") + " side", zm, { where: whereOf(row.cx) || "center" });
          }
          if (za > 5 && now > cool.audio) {
            cool.audio = now + 2500;
            liveEvent("audio", "a sound " + (db - median(history.db)).toFixed(0) + " dB above the room", za);
          }
          if (lightChange && now > cool.light) {
            cool.light = now + 2500; liveEvent("light_change", "the light changed suddenly", zl);
          }
        } catch (error) { stopRoom("Capture stopped after a measurement error: " + error.message); }
      }, STEP * 1000);
      current.starting = false;
      $("#rm-start").textContent = "Stop";
      $("#rm-seance-open").hidden = false;
    } catch (error) {
      acquired && acquired.getTracks().forEach((track) => track.stop());
      if (revision === roomRevision) stopRoom("Could not start camera and microphone: " + error.message);
    }
  }

  function stopRoom(message = "Camera and microphone stopped. No raw recording was stored. Any summaries already sent remain on the server.") {
    roomRevision++;
    const current = room, video = $("#rm-video");
    clearInterval(current.timer); clearTimeout(current.hauntTimer);
    current.stream && current.stream.getTracks().forEach((track) => track.stop());
    if (current.ac && current.ac.state !== "closed") current.ac.close().catch(() => {});
    video.pause(); video.srcObject = null;
    room = emptyRoom();
    resetBoard("rm");
    $("#rm-seance-open").hidden = true;
    $("#rm-haunt").hidden = true;
    $("#rm-meters").textContent = ""; $("#rm-log").textContent = "";
    $("#rm-start").textContent = "Turn on camera and microphone";
    $("#rm-status").textContent = message;
  }

  // ------------------------------------------------------------ boot
  function boot() {
    $("#uh-seance-slot").innerHTML = seanceUI("uh");
    $("#rm-seance-slot").innerHTML = seanceUI("rm");
    ["#uh-status", "#rm-status"].forEach((id) => {
      $(id).setAttribute("role", "status");
      $(id).setAttribute("aria-live", "polite");
      $(id).setAttribute("aria-atomic", "true");
    });
    const file = $("#uh-file"), label = file.closest("label");
    if (label) {
      label.setAttribute("role", "button"); label.tabIndex = 0;
      label.setAttribute("aria-controls", "uh-file");
      label.addEventListener("keydown", (event) => {
        if ((event.key === "Enter" || event.key === " ") && !file.disabled) {
          event.preventDefault(); file.click();
        }
      });
    }
    let cancel = $("#uh-cancel");
    if (!cancel) {
      cancel = document.createElement("button"); cancel.id = "uh-cancel";
      cancel.type = "button"; cancel.className = "big alt";
      $("#uh-demo").parentElement.appendChild(cancel);
    }
    cancel.textContent = "Cancel / end board"; cancel.hidden = true;
    cancel.addEventListener("click", () => {
      if (analysisController) {
        resetRecording();
        $("#uh-status").textContent = "Analysis cancelled. No new case was saved.";
      } else {
        resetBoard("uh");
        $("#uh-status").textContent = "The board or replay has ended. Measurements remain available.";
      }
      refreshUnheardControls();
    });
    const limits = document.createElement("p");
    limits.className = "notice";
    limits.textContent = "Recordings: up to 24 MiB and 90 seconds. Raw media stays in this browser. Relative intensity is a signal score, not a probability.";
    $("#uh-demo").parentElement.insertAdjacentElement("afterend", limits);
    $("#uh-demo").addEventListener("click", openDemo);
    file.addEventListener("change", async (event) => {
      const recording = event.target.files[0];
      event.target.value = "";
      if (!recording) return;
      await analyze(async (signal) => {
        checkFileSize(recording);
        $("#uh-story").textContent = "Your recording stays in this browser. Opening a board sends summaries, questions and optional memory text to the server.";
        await investigate(recording, recording.name, null, signal);
      });
    });
    $("#uh-open").addEventListener("click", () =>
      openBoard("uh", unheard.title || "recording", unheard.evidence, $("#uh-words").value.trim()));
    $("#uh-replay").addEventListener("click", replaySeance);
    $("#uh-dossier").addEventListener("click", dossier);
    ["uh", "rm"].forEach((prefix) => {
      $("#" + prefix + "-ask").addEventListener("submit", (event) => {
        event.preventDefault();
        const input = $("input", event.target), question = input.value.trim();
        if (!question || boards[prefix].busy) return;
        ask(prefix, question, prefix === "rm" ? () => { if (room.stream) room.watchUntil = performance.now() + 6000; } : undefined);
        input.value = "";
      });
    });
    $("#rm-start").addEventListener("click", () => (room.stream || room.starting ? stopRoom() : startRoom()));
    $("#rm-seance-open").addEventListener("click", () => openBoard("rm", "the room", room.evidence));
    window.addEventListener("pagehide", () => { resetRecording(); stopRoom(); });
    refreshUnheardControls();
  }
  boot();
})();
