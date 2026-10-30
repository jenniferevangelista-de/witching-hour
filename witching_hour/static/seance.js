/* The séance as a scene.
   The crew sits around the board. The spirit speaks only through the glass (three words at most).
   Luna, the medium, reads the glass out loud: that sentence is written by the model from the cited evidence.
   Dr. Bigotes checks it against the evidence. Xochi keeps watch. Each one talks in a speech bubble, with a voice
   recorded ahead of time (demo/make_seance_voices.py).
   In the recorded séance the board slowly spells I AM HERE under the Guardian's voice, the crew runs out and
   the page moves on to The Room.
   paranormal.js calls WH.stage when it exists; without this file the old behaviour is unchanged. */
(() => {
  "use strict";
  const WH = window.WH;
  if (!WH) return;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = () => WH.reduceMotion;
  const wait = (ms) => new Promise((r) => setTimeout(r, reduce() ? Math.min(ms, 700) : ms));
  const CREW = {
    luna: { name: "Luna", img: "/static/characters/luna.svg" },
    bigotes: { name: "Dr. Bigotes", img: "/static/characters/bigotes.svg" },
    xochi: { name: "Xochi", img: "/static/characters/xochi.svg" },
  };
  const MODE = { luna: "medium", bigotes: "skeptic", xochi: "family" };   // the Home cards use the story modes as classes
  const INTRO = {
    luna: "Shhh... the house is breathing. I am Luna, the medium. I feel every presence in my crystal ball.",
    bigotes: "Hmph. I am Doctor Bigotes. I have never met a ghost that was not a kettle, a draft or a thermostat.",
    xochi: "I am Xochi. I keep watch all night, and at dawn I bring the family a note about what I saw.",
  };

  // ---- sound, made in the browser (no files): knocks, heartbeat, a low drone, a door slam
  const sfx = (() => {
    let ac = null, master = null, droneNodes = null, beat = null, mus = null;
    let enabled = true, musicOn = true;
    try { enabled = localStorage.getItem("wh_sound") !== "off"; musicOn = localStorage.getItem("wh_music") !== "off"; } catch (_) { /* private mode */ }
    const ctx = () => {
      try {
        if (!ac) { ac = new (window.AudioContext || window.webkitAudioContext)(); master = ac.createGain(); master.gain.value = 0.5; master.connect(ac.destination); }
        if (ac.state === "suspended") ac.resume();
        return ac;
      } catch (_) { return null; }
    };
    const env = (g, t, a, d, peak) => {
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(peak, t + a);
      g.gain.exponentialRampToValueAtTime(0.0001, t + a + d);
    };
    function tone(type, f0, f1, dur, peak, delay = 0) {
      const c = enabled && ctx();
      if (!c) return;
      const t = c.currentTime + delay, o = c.createOscillator(), g = c.createGain();
      o.type = type;
      o.frequency.setValueAtTime(f0, t);
      if (f1) o.frequency.exponentialRampToValueAtTime(f1, t + dur);
      env(g, t, 0.005, dur, peak);
      o.connect(g); g.connect(master);
      o.start(t); o.stop(t + dur + 0.05);
    }
    function noise(dur, f0, f1, peak, delay = 0) {
      const c = enabled && ctx();
      if (!c) return;
      const t = c.currentTime + delay, n = Math.floor(c.sampleRate * dur), buf = c.createBuffer(1, n, c.sampleRate), d = buf.getChannelData(0);
      for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
      const src = c.createBufferSource(); src.buffer = buf;
      const bp = c.createBiquadFilter(); bp.type = "bandpass"; bp.Q.value = 0.9;
      bp.frequency.setValueAtTime(f0, t); bp.frequency.exponentialRampToValueAtTime(f1, t + dur);
      const g = c.createGain(); env(g, t, Math.min(0.05, dur / 3), dur, peak);
      src.connect(bp); bp.connect(g); g.connect(master); src.start(t);
    }
    const api = {
      get on() { return enabled; },
      set(v) {
        enabled = v;
        try { localStorage.setItem("wh_sound", v ? "on" : "off"); } catch (_) { /* ignore */ }
        if (!v) { api.drone(false); api.heart(false); api.music(false); stopVoice(); }
      },
      prime() { ctx(); },
      tick() { tone("triangle", 1400, 900, 0.06, 0.04); },
      letter() { tone("sine", 660, 520, 0.28, 0.05); },
      knock() { tone("sine", 120, 55, 0.12, 0.5); tone("sine", 110, 50, 0.12, 0.45, 0.17); },
      beat() { tone("sine", 62, 38, 0.2, 0.45); tone("sine", 58, 36, 0.22, 0.35, 0.22); },
      slam() { noise(0.5, 1800, 120, 0.7); tone("sine", 90, 30, 0.55, 0.8); },
      whoosh() { noise(0.9, 300, 3000, 0.25); },
      heart(on) {
        clearInterval(beat); beat = null;
        if (on) { api.beat(); beat = setInterval(api.beat, 1100); }
      },
      // a slow suspense score, made in the browser: a minor pad that changes chord, a music box with an echo, and now and then a wrong note
      get musicOn() { return musicOn; },
      setMusic(v) {   // the score has its own switch: the voices and effects stay
        musicOn = v;
        try { localStorage.setItem("wh_music", v ? "on" : "off"); } catch (_) { /* ignore */ }
        if (!v) api.music(false);
      },
      music(on) {
        if (!on) {
          if (mus) {
            const { g, c, timer, os } = mus;
            clearInterval(timer);
            g.gain.cancelScheduledValues(c.currentTime);
            g.gain.setTargetAtTime(0.0001, c.currentTime, 0.7);
            os.forEach((o) => { try { o.stop(c.currentTime + 3.5); } catch (_) { /* already stopped */ } });
            mus = null;
          }
          return;
        }
        const c = enabled && musicOn && ctx();
        if (!c || mus) return;
        const g = c.createGain(); g.gain.value = 0.0001; g.gain.setTargetAtTime(0.1, c.currentTime, 2.5); g.connect(master);
        const lp = c.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 520; lp.Q.value = 2;
        const padG = c.createGain(); padG.gain.value = 0.34;
        lp.connect(padG); padG.connect(g);
        const lfo = c.createOscillator(), lfoG = c.createGain(); lfo.frequency.value = 0.07; lfoG.gain.value = 260;
        lfo.connect(lfoG); lfoG.connect(lp.frequency); lfo.start();
        const CH = [[110, 130.8, 164.8], [87.3, 110, 130.8], [98, 123.5, 146.8], [82.4, 103.8, 123.5]];
        const os = [lfo];
        const pads = [0, 1, 2].map((i) => {
          const o = c.createOscillator(); o.type = i === 2 ? "sine" : "triangle"; o.frequency.value = CH[0][i]; o.detune.value = (i - 1) * 7;
          o.connect(lp); o.start(); os.push(o); return o;
        });
        const echo = c.createDelay(1.5); echo.delayTime.value = 0.46;
        const fb = c.createGain(); fb.gain.value = 0.46;
        const elp = c.createBiquadFilter(); elp.type = "lowpass"; elp.frequency.value = 2400;
        echo.connect(elp); elp.connect(fb); fb.connect(echo); elp.connect(g);
        const NOTES = [392, 440, 493.9, 523.3, 587.3, 659.3, 698.5], WRONG = [466.2, 622.3];
        let n = 0, last = 3;
        const bell = (f) => {
          const t = c.currentTime + 0.05, b = c.createGain();
          env(b, t, 0.012, 2.4, 0.2);
          [[f, 1], [f * 2, 0.25], [f * 3.01, 0.08]].forEach(([hz, a]) => {
            const o = c.createOscillator(), og = c.createGain(); o.type = "sine"; o.frequency.value = hz; og.gain.value = a;
            o.connect(og); og.connect(b); o.start(t); o.stop(t + 2.6);
          });
          b.connect(g); b.connect(echo);
        };
        const timer = setInterval(() => {
          n += 1;
          if (n % 9 === 1) { const ch = CH[((n / 9) | 0) % CH.length]; pads.forEach((o, i) => o.frequency.setTargetAtTime(ch[i], c.currentTime, 1.6)); }
          if (Math.random() < 0.5) {
            last = Math.max(0, Math.min(NOTES.length - 1, last + [-2, -1, -1, 1, 1, 2][(Math.random() * 6) | 0]));
            bell(Math.random() < 0.07 ? WRONG[(Math.random() * 2) | 0] : NOTES[last]);
          }
        }, 950);
        mus = { g, c, timer, os };
      },
      musicLevel(v) { if (mus) mus.g.gain.setTargetAtTime(v, mus.c.currentTime, 0.5); },
      drone(on) {
        if (!on) {
          if (droneNodes) {
            const { g, os, c } = droneNodes;
            g.gain.cancelScheduledValues(c.currentTime);
            g.gain.setTargetAtTime(0.0001, c.currentTime, 0.4);
            os.forEach((o) => o.stop(c.currentTime + 1.8));
            droneNodes = null;
          }
          return;
        }
        const c = enabled && ctx();
        if (!c || droneNodes) return;
        const g = c.createGain(); g.gain.value = 0.0001; g.gain.setTargetAtTime(0.06, c.currentTime, 0.8);
        const lp = c.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 260;
        const os = [55, 82.4, 110.6].map((f, i) => {
          const o = c.createOscillator(); o.type = i === 2 ? "sine" : "sawtooth"; o.frequency.value = f; o.detune.value = i * 6;
          o.connect(lp); o.start(); return o;
        });
        lp.connect(g); g.connect(master);
        droneNodes = { g, os, c };
      },
    };
    return api;
  })();

  // ---- the crew's voices: lines recorded ahead of time, looked up by their text
  const norm = (t) => String(t).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  let VOICES = {};
  fetch("/api/seance/voices").then((r) => (r.ok ? r.json() : {})).then((v) => { VOICES = v || {}; }).catch(() => { /* text only */ });
  const clipUrl = (text) => { const e = VOICES[norm(text)]; return e ? `/audio/${e.file}` : null; };
  let voiceEl = null;
  function stopVoice() { if (voiceEl) { try { voiceEl.pause(); } catch (_) { /* ignore */ } voiceEl = null; } }
  const metaOf = (a) => new Promise((res) => {
    const t = setTimeout(() => res(0), 1800);
    a.addEventListener("loadedmetadata", () => { clearTimeout(t); res(isFinite(a.duration) ? a.duration : 0); }, { once: true });
    a.addEventListener("error", () => { clearTimeout(t); res(0); }, { once: true });
  });
  const endedOf = (a, dur) => new Promise((r) => {
    if (a.ended) return r();
    a.addEventListener("ended", r, { once: true });
    a.addEventListener("error", r, { once: true });
    setTimeout(r, Math.max(500, (dur - a.currentTime) * 1000 + 700));
  });
  let typing = 0;

  /* Say one line: type it while the recorded voice plays (if there is one), then hold it long enough to read. */
  async function voiced(text, src, show, opts) {
    WH.active = (WH.active || 0) + 1;   // the page asks this before it leaves: anything still talking means a fresh start
    try { return await voicedLine(text, src, show, opts); } finally { WH.active -= 1; }
  }
  async function voicedLine(text, src, show, { hold = null, active = () => true } = {}) {
    const me = ++typing;
    const current = () => me === typing && active();
    if (!current()) return false;
    if (src) stopVoice();
    let audio = null, dur = 0;
    if (src && sfx.on) {
      const a = new Audio(src);
      a.preload = "auto";
      dur = await metaOf(a);
      if (!current()) { a.pause(); return false; }
      if (dur > 0) audio = a;
    }
    const per = reduce() ? 0 : dur ? Math.min(80, Math.max(20, (dur * 1000) / Math.max(text.length, 1))) : 42;
    if (!current()) return false;
    if (audio) { voiceEl = audio; audio.play().catch(() => { /* autoplay blocked */ }); }
    if (!per) show(text);
    else {
      for (let i = 1; i <= text.length; i++) {
        if (!current()) { if (audio) audio.pause(); return false; }
        show(text.slice(0, i));
        await new Promise((r) => setTimeout(r, per));
      }
    }
    if (audio) await endedOf(audio, dur);
    if (!current()) { if (audio) audio.pause(); return false; }
    await wait(hold != null ? hold : audio ? 550 : Math.max(1400, 34 * text.length));
    return current();
  }

  // ---- the scene around each board
  const S = {};
  const sceneGuard = (prefix, active) => {
    const st = S[prefix], epoch = st && st.epoch;
    return () => !!st && !st.cancelled && st.epoch === epoch &&
      (!st.active || st.active()) && (!active || active());
  };

  function build(prefix) {
    const root = $(`#${prefix}-seance`), board = $(`#${prefix}-board`);
    if (!root || !board || root.dataset.staged) return;
    root.dataset.staged = "1";
    root.classList.add("staged");
    // the séance needs the full width: take it out of the two-column layout
    const slot = $(`#${prefix}-seance-slot`), layout = slot && slot.closest(".layout");
    if (layout) layout.after(slot);
    const fiction = $(".fiction", root);
    if (fiction) fiction.hidden = true;   // the page already says once that the spirits are fiction
    const seat = (who, role) => `<figure class="seat ${who}" data-who="${who}"><div class="sbub"><small class="tag"></small><p></p></div><img src="${CREW[who].img}" alt="${CREW[who].name}"><figcaption>${CREW[who].name}<span>${role}</span></figcaption></figure>`;
    const how = document.createElement("p");
    how.className = "scene-how";
    how.innerHTML = "<b>How a séance works.</b> The spirit speaks only through the glass, three words at most. <b>Luna</b> reads the glass out loud (the sentence is written by the model from the evidence). <b>Dr. Bigotes</b> checks it against what was really measured. <b>Xochi</b> keeps watch.";
    const stage = document.createElement("div");
    stage.className = "stage";
    stage.id = `${prefix}-stage`;
    stage.innerHTML = `<div class="corner l"></div><div class="corner r"></div>
      <div class="candle c1" aria-hidden="true"><i></i></div><div class="candle c2" aria-hidden="true"><i></i></div>
      ${seat("bigotes", "checks the evidence")}
      <div class="mid">${seat("luna", "reads the glass")}<div class="slot"></div></div>
      ${seat("xochi", "keeps watch")}`;
    board.before(how);
    how.after(stage);
    $(".slot", stage).append(board);
    const glass = $(".glass", board);
    if (glass) WH.placeGlass(glass, "REST");   // the glass rests on the board until it is called
    // the buttons that start the show live inside the scene
    if (prefix === "uh") {
      const replay = $("#uh-replay"), open = $("#uh-open");
      if (replay) { replay.classList.add("fab"); $(".corner.l", stage).append(replay); }
      void open;   // the real button is hidden: the fixed one at the top does its job
    }
    const spelled = $(`#${prefix}-spelled`);
    if (spelled) stage.after(spelled);
    const speech = document.createElement("div");   // the same lines as plain text, for small screens
    speech.className = "speech";
    speech.innerHTML = '<img class="who" alt=""><div><b class="name"></b><span class="tag"></span><p class="said"></p></div>';
    (spelled || stage).after(speech);
    const ctl = document.createElement("div");
    ctl.className = "scene-ctl";
    ctl.innerHTML = `<button type="button" class="snd"></button><button type="button" class="skip" hidden>⏭ Skip to the ending</button><button type="button" class="go" hidden>Go to The Room →</button>`;
    speech.after(ctl);
    if (prefix === "uh") {
      const dossier = $("#uh-dossier");
      const card = document.createElement("div");
      card.className = "dossier-cta";
      card.innerHTML = `<img src="${CREW.xochi.img}" alt="Xochi"><div><b>Xochi writes it all down</b><span>A one-page report: what the camera measured, what Dr. Bigotes thinks, and what the board said.</span></div>`;
      if (dossier) { dossier.classList.remove("alt"); card.append(dossier); }
      ctl.after(card);
    }
    const st = S[prefix] = { root, stage, speech, ctl, epoch: 0, active: null, count: 0, skip: false, cancelled: false, quipped: new Set(), letters: 0, audio: null, turnAudio: null };
    const label = () => { $(".snd", ctl).textContent = sfx.on ? "🔊 Sound on" : "🔇 Sound off"; };
    label();
    $(".snd", ctl).addEventListener("click", () => { sfx.set(!sfx.on); label(); });
    $(".skip", ctl).addEventListener("click", () => { st.skip = true; $(".skip", ctl).hidden = true; });
    $(".go", ctl).addEventListener("click", () => window.WHNav && window.WHNav.go("room"));
  }

  /* One character says one line, in a bubble above the character (and in the strip on small screens). */
  async function say(prefix, who, text, { tag = "", clip = null, url = null, silent = false, hold = null, active } = {}) {
    const st = S[prefix];
    const current = sceneGuard(prefix, active);
    if (!current()) return false;
    const seat = $(`.seat.${who}`, st.stage);
    $$(".sbub", st.stage).forEach((b) => b.classList.remove("on"));
    $$(".seat", st.stage).forEach((s) => s.classList.toggle("speaking", s === seat));
    const bubble = $(".sbub", seat), p = $("p", bubble);
    $(".tag", bubble).textContent = tag;
    p.textContent = "";
    bubble.classList.add("on");
    const strip = st.speech;
    strip.dataset.who = who;
    $(".who", strip).src = CREW[who].img;
    $(".who", strip).alt = CREW[who].name;
    $(".name", strip).textContent = CREW[who].name;
    $(".tag", strip).textContent = tag;
    strip.classList.add("on");
    const src = silent ? null : url || clipUrl(clip || text);
    const completed = await voiced(text, src, (t) => { if (current()) { p.textContent = t; $(".said", strip).textContent = t; } }, { hold, active: current });
    return completed && current();
  }

  const shake = (el) => { if (reduce()) return; el.classList.remove("shake"); void el.offsetWidth; el.classList.add("shake"); setTimeout(() => el.classList.remove("shake"), 600); };

  function trail(boardEl, ms) {
    if (reduce()) return;
    const current = sceneGuard(prefixOf(boardEl));
    const g = $(".glass", boardEl), t0 = performance.now();
    const id = setInterval(() => {
      if (!current() || performance.now() - t0 > ms) { clearInterval(id); return; }
      const gr = g.getBoundingClientRect(), br = boardEl.getBoundingClientRect();
      const d = document.createElement("i");
      d.className = "spark";
      d.style.left = `${gr.left + gr.width / 2 - br.left}px`;
      d.style.top = `${gr.top + gr.height * 0.45 - br.top}px`;
      boardEl.append(d);
      d.addEventListener("animationend", () => d.remove());
    }, 45);
  }

  function light(boardEl, ch) {
    $$("svg text", boardEl).filter((t) => t.textContent.trim() === ch).forEach((t) => {
      t.classList.add("lit");
      setTimeout(() => t.classList.remove("lit"), 1400);
    });
  }

  function flash() {
    if (reduce()) return;
    const f = document.createElement("div");
    f.className = "flash";
    document.body.append(f);
    f.addEventListener("animationend", () => f.remove());
  }

  const prefixOf = (boardEl) => (boardEl.id || "").replace("-board", "");

  // ---- the climax: the board slowly spells I AM HERE
  async function prelude(prefix, opts) {
    const st = S[prefix];
    const current = sceneGuard(prefix, opts.active);
    if (!current()) return false;
    document.body.classList.add("climax");
    st.stage.classList.add("climax");
    st.audio = opts.audioUrl || null;
    st.letters = 0;
    sfx.drone(true);
    sfx.musicLevel(0.04);
    sfx.knock(); shake(st.stage);
    await wait(900);
    if (!current()) return false;
    sfx.knock(); shake(st.stage);
    await wait(700);
    if (!current()) return false;
    if (!await say(prefix, "xochi", "Wait. The air just changed.", { tag: "Xochi keeps watch", active: current })) return false;
    if (!await say(prefix, "bigotes", "It is only a draft. Probably.", { tag: "Dr. Bigotes", active: current })) return false;
    sfx.heart(true);
    st.stage.classList.add("hush");
    $$(".sbub", st.stage).forEach((b) => b.classList.remove("on"));
    st.speech.classList.add("hush");
    await wait(700);
    return current();
  }

  // ---- the finale: lights out, the crew runs, the page moves on to The Room
  async function finale(prefix, opts = {}) {
    const st = S[prefix];
    const current = sceneGuard(prefix, opts.active);
    if (!current() || st.finaleRunning) return false;
    st.finaleRunning = true;
    sfx.heart(false); sfx.drone(false); sfx.music(false);
    sfx.slam(); flash(); shake(st.stage);
    const dark = document.createElement("div");
    dark.className = "lights-out";
    document.body.append(dark);
    dark.addEventListener("animationend", () => dark.remove());
    $$(".seat", st.stage).forEach((s) => s.classList.add("scared"));
    await wait(1100);
    if (!current()) return false;
    sfx.whoosh();
    $$(".seat", st.stage).forEach((s) => { s.classList.remove("scared"); s.classList.add("run"); });
    const burst = document.createElement("div");   // comic lettering over the stage while they run
    burst.className = "runtext"; burst.setAttribute("aria-hidden", "true");
    burst.innerHTML = "<span>RUN!</span><span>RUN!</span><span>RUUUUN!!</span>";
    st.stage.append(burst);
    setTimeout(() => burst.remove(), 3600);
    const card = $("#act-card") || (() => {
      const c = document.createElement("div");
      c.id = "act-card"; c.className = "act"; c.hidden = true;
      c.innerHTML = '<div><p class="kicker">The séance is over</p><h2>Now it is your turn</h2><p>The glass can only say what the camera really measured. Bring your own recording and see what yours was trying to tell you.</p><div class="end-actions"><button type="button" class="big tryit">Try it yourself</button><button type="button" class="big alt next">Continue to The Room →</button></div><button type="button" class="stay">Stay in the séance</button></div>';
      document.body.append(c);
      return c;
    })();
    const lines = [["luna", "Out! Everybody out!"], ["bigotes", "Fine! I have nothing left to say! Run, run, RUUUUN!"], ["xochi", "Stay close to me!"]];
    // while the crew runs, each one shouts from where they stand
    const running = (async () => { for (const [w, t] of lines) { if (!current() || !await say(prefix, w, t, { tag: "", hold: 150, active: current })) return false; } return true; })();
    await Promise.all([running, wait(2200)]);
    if (!current()) return false;
    st.stage.classList.remove("hush");
    card.hidden = false;
    setTimeout(() => { if (current()) card.classList.add("show"); }, 30);
    document.body.classList.add("act-on");
    const choice = await new Promise((res) => {
      st.resolveFinale = res;
      $(".tryit", card).onclick = () => { if (current()) res("try"); };
      $(".next", card).onclick = () => { if (current()) res("next"); };
      $(".stay", card).onclick = () => { if (current()) res("stay"); };
    });
    if (!current()) return false;
    st.resolveFinale = null;
    card.classList.remove("show");
    document.body.classList.remove("act-on");
    setTimeout(() => { if (current()) card.hidden = true; }, 500);
    st.finaleRunning = false;
    if (choice === "next") {
      WH.stage.close(prefix);
      if (window.WHNav) window.WHNav.go("room");
      return;
    }
    $$(".seat", st.stage).forEach((x) => x.classList.remove("run", "scared"));
    WH.stage.close(prefix);
    document.body.classList.remove("summoned");
    st.root.classList.remove("live");
    if (choice === "try") {
      const target = $("#uh-file") && $("#uh-file").closest("label") || $("#uh-demo");
      if (target) {
        target.scrollIntoView({ behavior: reduce() ? "auto" : "smooth", block: "center" });
        target.classList.add("nudge");
        setTimeout(() => target.classList.remove("nudge"), 4000);
      }
    } else {
      $(".go", st.ctl).hidden = false;
    }
  }

  WH.stage = {
    open(prefix, opts = {}) {
      build(prefix);
      const st = S[prefix];
      if (!st) return;
      if (opts.active && !opts.active()) return;
      st.epoch++; st.active = opts.active || null;
      st.skip = false; st.cancelled = false; st.count = 0; st.quipped = new Set();
      $$(".seat", st.stage).forEach((s) => s.classList.remove("run", "scared"));
      st.root.classList.remove("live");
      st.root.classList.add("replaying");
      $(".go", st.ctl).hidden = true;
      $(".skip", st.ctl).hidden = false;
      const fab = $("#uh-replay"); if (fab && prefix === "uh") fab.classList.add("off");
      document.body.classList.add("seance-on");
      sfx.prime();
      st.root.scrollIntoView({ behavior: reduce() ? "auto" : "smooth", block: "start" });
    },
    close(prefix) {
      const st = S[prefix];
      if (!st) return;
      st.epoch++; st.cancelled = true; st.active = null;
      typing++; stopVoice();
      if (st.climaxVoice) st.climaxVoice.pause();
      st.climaxVoice = null; st.audio = null; st.turnAudio = null;
      if (st.resolveFinale) { st.resolveFinale("cancel"); st.resolveFinale = null; }
      st.finaleRunning = false;
      const card = $(prefix === "uh" ? "#act-card" : "#end-card");
      if (card) { card.classList.remove("show"); card.hidden = true; }
      document.body.classList.remove("act-on");
      $$(".flash, .lights-out").forEach((el) => el.remove());
      $$(".runtext, .spark", st.stage).forEach((el) => el.remove());
      $(".skip", st.ctl).hidden = true;
      st.root.classList.remove("replaying", "live");
      document.body.classList.remove("seance-on", "climax", "summoned");
      st.stage.classList.remove("climax", "hush");
      st.speech.classList.remove("hush", "on");
      $$(".seat", st.stage).forEach((s) => s.classList.remove("speaking", "lean", "run", "scared"));
      $$(".sbub", st.stage).forEach((b) => b.classList.remove("on"));
      $$(".sbub p, .sbub .tag", st.stage).forEach((el) => { el.textContent = ""; });
      $$(".name, .tag, .said", st.speech).forEach((el) => { el.textContent = ""; });
      const fab = $("#uh-replay"); if (fab && prefix === "uh") fab.classList.remove("off");
      sfx.heart(false); sfx.drone(false); sfx.music(false);
    },
    live(prefix, opts = {}) {   // a spirit has been summoned: the visitor can ask
      build(prefix);
      const st = S[prefix];
      if (!st) return;
      if (opts.active && !opts.active()) return;
      st.epoch++; st.active = opts.active || null; st.cancelled = false;
      st.root.classList.add("live");
      if (prefix === "uh") document.body.classList.add("summoned");
      st.count = 0; st.quipped = new Set();
    },
    skipping(prefix) { return !!(S[prefix] && S[prefix].skip); },
    cancelled(prefix) { return !!(S[prefix] && S[prefix].cancelled); },

    async ask(prefix, question, opts = {}) {
      build(prefix);
      const current = sceneGuard(prefix, opts.active);
      if (!current()) return false;
      document.body.classList.add("seance-on");
      sfx.prime();
      return say(prefix, "luna", question, { tag: "Luna asks the board", active: current });
    },
    async begin(prefix, r, opts = {}) {
      build(prefix);
      const st = S[prefix];
      const current = sceneGuard(prefix, opts.active);
      if (!current()) return false;
      if (opts.climax && !opts.audioUrl) opts = { ...opts, audioUrl: clipUrl(r.response.spoken) };   // live game: the recorded Guardian line
      st.turnAudio = opts.climax ? null : opts.audioUrl || null;
      $$(".seat", st.stage).forEach((s) => s.classList.add("lean"));
      if (opts.climax) { if (!await prelude(prefix, { ...opts, active: current })) return false; }
      else if (opts.finale) { st.stage.classList.remove("climax"); document.body.classList.remove("climax"); }
      else sfx.knock();
      return current();
    },
    glass(boardEl, ch, slow) {
      if (!sceneGuard(prefixOf(boardEl))()) return;
      trail(boardEl, slow ? 1400 : 650);
      light(boardEl, ch);
      sfx.tick();
    },
    letter(boardEl, ch, slow) {
      if (!sceneGuard(prefixOf(boardEl))()) return;
      sfx.letter();
      if (!slow) return;
      const st = S[prefixOf(boardEl)];
      if (!st) return;
      shake(boardEl);
      st.letters += 1;
      if (st.letters === 4 && st.audio && sfx.on) {
        stopVoice();
        const a = new Audio(st.audio);
        a.volume = 0.95;
        voiceEl = a;
        st.climaxVoice = a;
        a.play().catch(() => { /* autoplay blocked */ });
      }
    },
    async read(prefix, r, opts = {}) {
      const st = S[prefix];
      const current = sceneGuard(prefix, opts.active);
      if (!current()) return false;
      st.speech.classList.remove("hush");
      st.stage.classList.remove("hush");
      if (opts.finale) return finale(prefix, { ...opts, active: current });
      if (opts.climax && st.climaxVoice) {   // let the Guardian finish before Luna reads it
        const a = st.climaxVoice;
        st.climaxVoice = null;
        await endedOf(a, isFinite(a.duration) ? a.duration : 6);
        if (!current()) return false;
      }
      const ids = (r.grounding && r.grounding.related_evidence_ids) || [];
      const by = String(r.response.by || "unknown source");
      const source = /template|scripted/i.test(by) ? "scripted reading" : by.trim().slice(0, 60);
      const spoken = r.response.spoken;
      // the recorded voice already played under the board in the climax; the reading is only shown, slowly
      if (spoken) {
        if (!await say(prefix, "luna", spoken, { tag: `Luna reads the glass · ${source}`, clip: spoken, url: st.turnAudio, silent: !!opts.climax, hold: opts.climax ? 2200 : null, active: current })) return false;
      }
      const all = WH.evidenceFor(prefix);
      const e = ids.map((i) => all.find((x) => x.id === i)).find((x) => x && !st.quipped.has(x.id));
      const citedSounds = ids.map((id) => all.find((event) => event.id === id)).filter((event) => event && event.type === "audio");
      if (opts.climax && opts.recorded && citedSounds.length === 2) {
        if (!await say(prefix, "bigotes", "Two real sounds, both cited. And I have no kettle for this.", { tag: "Dr. Bigotes", active: current })) return false;
      } else if (e) {
        st.quipped.add(e.id);
        const note = WH.bigotes(e, all);
        if (!await say(prefix, "bigotes", note, { tag: `Dr. Bigotes checks ${e.id} · ${e.start.toFixed(2)} s`, clip: note, active: current })) return false;
      }
      st.count += 1;
      const xochi = ["I kept watch. The glass moved by itself.", "Her words are gentle. Her warning is not.", "I will write it down: every answer cites a real moment."];
      if (!opts.climax && st.count % 3 === 1) { if (!await say(prefix, "xochi", xochi[((st.count - 1) / 3 | 0) % xochi.length], { tag: "Xochi keeps watch", active: current })) return false; }
      return current();
    },
    roomIntro(prefix, opts = {}) {
      build(prefix);
      const st = S[prefix];
      const current = sceneGuard(prefix, opts.active);
      if (!current()) return false;
      st.scared = false;
      document.body.classList.add("seance-on");
      sfx.prime();
      st.root.scrollIntoView({ behavior: reduce() ? "auto" : "smooth", block: "start" });
      return say(prefix, "luna", "The room is yours now. Ask the board, and watch the glass.", { tag: "Luna", active: current });
    },
    async roomScare(prefix, opts = {}) {   // the last act: the room moves when the glass stops
      const st = S[prefix];
      const current = sceneGuard(prefix, opts.active);
      if (!current() || st.scared) return false;
      st.scared = true;
      await wait(2800);
      if (!current()) return false;
      sfx.music(false); sfx.slam(); flash(); shake(st.stage);
      if (WH.haunt) WH.haunt();
      const dark = document.createElement("div");
      dark.className = "lights-out";
      document.body.append(dark);
      dark.addEventListener("animationend", () => dark.remove());
      $$(".seat", st.stage).forEach((s) => s.classList.add("scared"));
      await wait(2200);
      if (!current()) return false;
      $$(".seat", st.stage).forEach((s) => s.classList.remove("scared"));
      if (!await say(prefix, "luna", "That was not me!", { tag: "Luna", active: current })) return false;
      if (!await say(prefix, "bigotes", "Probably the kettle. Probably.", { tag: "Dr. Bigotes", active: current })) return false;
      if (!await say(prefix, "xochi", "It moved when the glass stopped. I will write it down.", { tag: "Xochi keeps watch", active: current })) return false;
      if (!await say(prefix, "xochi", "The case is closed. Thank you for staying until the end.", { tag: "Xochi", active: current })) return false;
      if (!current()) return false;
      endCard();
    },
    async end(prefix, r, opts = {}) {
      const st = S[prefix];
      if (!sceneGuard(prefix, opts.active)()) return false;
      $$(".seat", st.stage).forEach((s) => s.classList.remove("lean", "speaking"));
      $$(".sbub", st.stage).forEach((b) => b.classList.remove("on"));
    },
  };

  function endCard() {
    let c = $("#end-card");
    if (!c) {
      c = document.createElement("div");
      c.id = "end-card"; c.className = "act end"; c.hidden = true;
      c.innerHTML = '<div><p class="kicker">The end</p><h2>Case closed</h2><p>A house, a recording, a room. The measurements were real. The spirits were not.</p><div class="end-actions"><button type="button" class="big again">Play again</button><button type="button" class="big alt tested">How it was tested</button><button type="button" class="stay">Close</button></div></div>';
      document.body.append(c);
      const close = (go) => { c.classList.remove("show"); setTimeout(() => { c.hidden = true; }, 500); if (go && window.WHNav) window.WHNav.go(go); };
      $(".again", c).onclick = () => close("home");
      $(".tested", c).onclick = () => close("lab");
      $(".stay", c).onclick = () => close();
    }
    c.hidden = false;
    requestAnimationFrame(() => c.classList.add("show"));
  }

  // The Room without a camera
  function roomButton() {
    const start = $("#rm-start");
    if (!start || $("#rm-demo")) return;
    const b = document.createElement("button");
    b.type = "button"; b.id = "rm-demo"; b.className = "big fab";
    b.textContent = "▶ Play without a camera";
    b.addEventListener("click", () => { sfx.prime(); if (WH.roomDemo) WH.roomDemo(); });
    start.after(b);
  }

  // ---- Summon the spirit: one button fixed at the top of The Unheard and one in Luna's panel, both there from the start
  function summonFixed() {
    const open = $("#uh-open");
    if (!open || $("#summon-fixed")) return;
    const label = "🔮 Summon the spirit";
    const mk = (id, cls) => { const b = document.createElement("button"); b.type = "button"; b.id = id; b.className = cls; b.textContent = label; return b; };
    const fixed = mk("summon-fixed", "big summon-fixed"), panel = mk("summon-panel", "big summon-panel");
    open.after(panel);   // the floating twin is not added to the page: it hid the proof banner
    const both = [fixed, panel];
    let waiting = false;
    const click = async () => {
      if (waiting) return;
      const status = $("#uh-status");
      const state = status && status.dataset.state;
      if (state === "loading" || state === "error" || state === "ready" && open.disabled) return;
      sfx.prime();
      if (state === "ready" && !open.hidden) { open.click(); return; }
      // Only an untouched page may offer the demo. Quiet or failed uploads stay separate.
      if (state !== "empty") return;
      waiting = true;
      both.forEach((b) => b.classList.add("wait"));
      const demoButton = $("#uh-demo");
      if (!demoButton || demoButton.disabled) {
        waiting = false; both.forEach((b) => b.classList.remove("wait")); return;
      }
      demoButton.click();
      const version = status.dataset.recordingVersion;
      const current = () => status.dataset.recordingVersion === version;
      const tick = setInterval(() => {
        if (!current()) return;
        const m = /Reading frames\.\.\. \d+%/.exec(status.textContent);
        both.forEach((b) => { b.textContent = "... " + (m ? m[0] : "Reading the recording..."); });
      }, 300);
      for (let i = 0; i < 240 && current() && status.dataset.state === "loading"; i++) {
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      clearInterval(tick);
      both.forEach((b) => { b.classList.remove("wait"); b.textContent = label; });
      waiting = false;
      if (current() && status.dataset.state === "ready" && !open.hidden && !open.disabled) open.click();
    };
    both.forEach((b) => b.addEventListener("click", click));
  }

  // ---- the evidence cards come out of the dark as you scroll down to them, each with a small ghost
  function ghostReveal() {
    if (!("IntersectionObserver" in window) || reduce()) return;
    let batch = 0, reset = null;
    const io = new IntersectionObserver((list) => {
      list.forEach((en) => {
        if (!en.isIntersecting) return;
        const el = en.target;
        io.unobserve(el);
        el.style.setProperty("--d", `${batch * 380}ms`);
        batch += 1;
        el.classList.add("in");
        clearTimeout(reset);
        reset = setTimeout(() => { batch = 0; }, 700);
      });
    }, { threshold: 0.25 });
    const watch = (el) => { if (el.classList.contains("event") && !el.dataset.g) { el.dataset.g = "1"; el.classList.add("pre"); io.observe(el); } };
    const scan = () => $$(".events > .event").forEach(watch);
    new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
    scan();
  }

  // Luna reads her own panel aloud when the case is ready (and on request)
  const LUNA_PANEL = "I summon the spirit the evidence suggests: a Guardian, a Lost One, a Trickster, a Watcher, a Hostile Presence or a Silent One. Its answers are fiction, and each one must point at a real moment of the recording.";
  function lunaPanel() {
    const box = $("#unheard .with-guide.luna, .terminal .with-guide.luna");
    if (!box || box.dataset.said) return;
    box.dataset.said = "1";
    const text = $("p.notice", box);
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "hear"; btn.textContent = "▶ Hear Luna";
    box.querySelector("div").append(btn);
    const status = $("#uh-status"), open = $("#uh-open");
    let busyNow = false, panelEpoch = 0, panelTimer = null;
    const speak = async (version = status.dataset.recordingVersion, stageEpoch = S.uh && S.uh.epoch) => {
      if (busyNow || !open || open.disabled || status.dataset.state !== "ready" ||
          version !== status.dataset.recordingVersion || stageEpoch !== (S.uh && S.uh.epoch)) return;
      const epoch = ++panelEpoch;
      const active = () => panelEpoch === epoch && version === status.dataset.recordingVersion &&
        stageEpoch === (S.uh && S.uh.epoch) && status.dataset.state === "ready" && !open.disabled;
      busyNow = true;
      sfx.prime();
      box.classList.add("talking");
      try { await voiced(LUNA_PANEL, clipUrl(LUNA_PANEL), () => {}, { hold: 300, active }); }
      finally { if (panelEpoch === epoch) { box.classList.remove("talking"); busyNow = false; } }
    };
    btn.addEventListener("click", () => speak());
    document.addEventListener("wh:recordingchange", () => {
      clearTimeout(panelTimer); panelTimer = null; panelEpoch++; busyNow = false;
      box.classList.remove("talking");
    });
    if (open) {
      let done = false;
      const mo = new MutationObserver(() => {
        if (!open.hidden && !done && status.dataset.state === "ready") {
          done = true;
          const version = status.dataset.recordingVersion, stageEpoch = S.uh && S.uh.epoch;
          if (sfx.on) panelTimer = setTimeout(() => { panelTimer = null; speak(version, stageEpoch); }, 600);
        }
      });
      mo.observe(open, { attributes: true, attributeFilter: ["hidden"] });
    }
    void text;
  }

  // the music switch: a small pill that stays on screen
  (() => {
    const b = document.createElement("button");
    b.type = "button"; b.id = "music-switch"; b.className = "music-switch";
    const label = () => { b.textContent = sfx.musicOn ? "🎵 Music: on" : "🔇 Music: off"; b.setAttribute("aria-pressed", String(sfx.musicOn)); };
    label();
    b.addEventListener("click", () => { sfx.setMusic(!sfx.musicOn); label(); if (sfx.musicOn && (document.body.classList.contains("seance-on") || document.body.classList.contains("summoned") || S.uh && S.uh.root.classList.contains("live"))) { sfx.prime(); sfx.music(true); } });
    document.body.append(b);
  })();

  // the suspense score starts with the first click that opens a case or a séance
  document.addEventListener("click", (e) => {
    const b = e.target.closest("#uh-demo, #uh-replay, #summon-fixed, #summon-panel, #rm-demo, #start-here, #rm-seance-open, #uh-file");
    if (b) { sfx.prime(); sfx.music(true); }
  });

  // ---- the idle scene is visible as soon as there is something to play
  function reveal() {
    const root = $("#uh-seance"), btns = ["#uh-replay", "#uh-open"].map((q) => $(q)).filter(Boolean);
    if (!root || !btns.length) return;
    const sync = () => { if (btns.some((b) => !b.hidden)) { root.hidden = false; root.classList.add("idle"); } };
    const mo = new MutationObserver(sync);
    btns.forEach((b) => mo.observe(b, { attributes: true, attributeFilter: ["hidden"] }));
    sync();
  }

  // ---- the crew introduces themselves, on request
  async function intro(who) {
    const card = $(`#crew .card.${MODE[who]}`);
    if (!card) return;
    $$("#crew .card").forEach((c) => c.classList.toggle("talking", c === card));
    let p = $(".intro", card);
    if (!p) { p = document.createElement("p"); p.className = "intro"; ($("q", card) || card.lastElementChild).after(p); }
    p.textContent = "";
    sfx.prime();
    await voiced(INTRO[who], clipUrl(INTRO[who]), (t) => { p.textContent = t; }, { hold: 500 });
    card.classList.remove("talking");
  }
  async function meetAll() {
    for (const who of ["luna", "bigotes", "xochi"]) {
      await intro(who);
      await wait(250);
    }
  }
  function crewButtons() {
    const crew = $("#crew");
    if (!crew || crew.dataset.meet) return;
    if (!$$(".card", crew).length) return;
    crew.dataset.meet = "1";
    $$(".card", crew).forEach((card) => {
      const who = ["luna", "bigotes", "xochi"].find((w) => card.classList.contains(MODE[w]));
      if (!who) return;
      const b = document.createElement("button");
      b.type = "button"; b.className = "hear"; b.textContent = "▶ Hear me";
      b.addEventListener("click", () => intro(who));
      card.append(b);
    });
    const row = document.createElement("div");
    row.className = "crew-ctl";
    row.innerHTML = '<button type="button" class="big alt meet">🎙️ Meet the crew, with voices</button>';
    crew.after(row);
    $(".meet", row).addEventListener("click", meetAll);
  }

  // build once now, so the crew is in place the moment the séance opens
  ["uh", "rm"].forEach(build);
  roomButton();
  summonFixed();
  lunaPanel();
  ghostReveal();
  reveal();
  crewButtons();
  const crewBox = $("#crew");
  if (crewBox) {
    const obs = new MutationObserver(() => { crewButtons(); if (crewBox.dataset.meet) obs.disconnect(); });
    obs.observe(crewBox, { childList: true });
  }
})();
