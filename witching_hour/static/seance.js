/* The séance as a scene.
   The crew sits around the board. The spirit speaks only through the glass (three words at most).
   Luna, the medium, reads the glass out loud: that sentence is written by the model from the cited evidence.
   Dr. Bigotes checks it against the evidence. Xochi keeps watch.
   In the recorded séance the board slowly spells I AM HERE under the Guardian's voice, the crew runs out
   and the page moves on to The Room.
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

  // ---- sound, made in the browser (no files): knocks, heartbeat, a low drone, a door slam
  const sfx = (() => {
    let ac = null, master = null, droneNodes = null, beat = null;
    let enabled = true;
    try { enabled = localStorage.getItem("wh_sound") !== "off"; } catch (_) { /* private mode */ }
    const ctx = () => {
      try {
        if (!ac) { ac = new (window.AudioContext || window.webkitAudioContext)(); master = ac.createGain(); master.gain.value = 0.55; master.connect(ac.destination); }
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
        if (!v) { api.drone(false); api.heart(false); }
      },
      prime() { ctx(); },
      tick() { tone("triangle", 1400, 900, 0.06, 0.05); },
      letter() { tone("sine", 660, 520, 0.28, 0.07); },
      knock() { tone("sine", 120, 55, 0.12, 0.5); tone("sine", 110, 50, 0.12, 0.45, 0.17); },
      beat() { tone("sine", 62, 38, 0.2, 0.5); tone("sine", 58, 36, 0.22, 0.4, 0.22); },
      slam() { noise(0.5, 1800, 120, 0.7); tone("sine", 90, 30, 0.55, 0.8); },
      whoosh() { noise(0.9, 300, 3000, 0.25); },
      heart(on) {
        clearInterval(beat); beat = null;
        if (on) { api.beat(); beat = setInterval(api.beat, 1100); }
      },
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
        const g = c.createGain(); g.gain.value = 0.0001; g.gain.setTargetAtTime(0.07, c.currentTime, 0.8);
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

  // ---- the scene around each board
  const S = {};
  let typing = 0;

  function build(prefix) {
    const root = $(`#${prefix}-seance`), board = $(`#${prefix}-board`);
    if (!root || !board || root.dataset.staged) return;
    root.dataset.staged = "1";
    root.classList.add("staged");
    // the séance needs the full width: take it out of the two-column layout
    const slot = $(`#${prefix}-seance-slot`), layout = slot && slot.closest(".layout");
    if (layout) layout.after(slot);
    const seat = (who, role) => `<figure class="seat ${who}" data-who="${who}"><img src="${CREW[who].img}" alt="${CREW[who].name}"><figcaption>${CREW[who].name}<span>${role}</span></figcaption></figure>`;
    const how = document.createElement("p");
    how.className = "scene-how";
    how.innerHTML = "<b>How a séance works.</b> The spirit speaks only through the glass, three words at most. <b>Luna</b> reads the glass out loud (the sentence is written by the model from the evidence). <b>Dr. Bigotes</b> checks it against what was really measured. <b>Xochi</b> keeps watch.";
    const scene = document.createElement("div");
    scene.className = "scene";
    scene.id = `${prefix}-scene`;
    scene.innerHTML = `<div class="candle c1" aria-hidden="true"><i></i></div><div class="candle c2" aria-hidden="true"><i></i></div>
      ${seat("bigotes", "checks the evidence")}
      <div class="mid">${seat("luna", "reads the glass")}<div class="slot"></div></div>
      ${seat("xochi", "keeps watch")}`;
    board.before(how);
    how.after(scene);
    $(".slot", scene).append(board);
    const speech = document.createElement("div");
    speech.className = "speech";
    speech.innerHTML = '<img class="who" alt=""><div><b class="name"></b><span class="tag"></span><p class="said"></p></div>';
    const spelled = $(`#${prefix}-spelled`);
    if (spelled) scene.after(spelled);
    (spelled || scene).after(speech);
    const ctl = document.createElement("div");
    ctl.className = "scene-ctl";
    ctl.innerHTML = `<button type="button" class="snd"></button><button type="button" class="skip" hidden>⏭ Skip to the ending</button><button type="button" class="go" hidden>Go to The Room →</button>`;
    speech.after(ctl);
    const st = S[prefix] = { root, scene, speech, ctl, count: 0, skip: false, cancelled: false, quipped: new Set(), letters: 0, audio: null };
    const label = () => { $(".snd", ctl).textContent = sfx.on ? "🔊 Sound on" : "🔇 Sound off"; };
    label();
    $(".snd", ctl).addEventListener("click", () => { sfx.set(!sfx.on); label(); });
    $(".skip", ctl).addEventListener("click", () => { st.skip = true; $(".skip", ctl).hidden = true; });
    $(".go", ctl).addEventListener("click", () => window.WHNav && window.WHNav.go("room"));
  }

  async function say(prefix, who, text, { tag = "", hold = 700, speed = 20 } = {}) {
    const st = S[prefix];
    if (!st) return;
    const el = st.speech, me = ++typing;
    el.dataset.who = who;
    $(".who", el).src = CREW[who].img;
    $(".who", el).alt = CREW[who].name;
    $(".name", el).textContent = CREW[who].name;
    $(".tag", el).textContent = tag;
    el.classList.add("on");
    $$(".seat", st.scene).forEach((s) => s.classList.toggle("speaking", s.dataset.who === who));
    const p = $(".said", el);
    if (reduce()) p.textContent = text;
    else {
      p.textContent = "";
      for (let i = 1; i <= text.length; i++) {
        if (me !== typing) return;
        p.textContent = text.slice(0, i);
        await new Promise((r) => setTimeout(r, speed));
      }
    }
    await wait(hold);
  }

  const firstSentence = (t) => { const s = String(t).split(/(?<=[.?!])\s+/)[0]; return s.length > 130 ? s.slice(0, 127) + "..." : s; };
  const shake = (el) => { if (reduce()) return; el.classList.remove("shake"); void el.offsetWidth; el.classList.add("shake"); setTimeout(() => el.classList.remove("shake"), 600); };

  function trail(boardEl, ms) {
    if (reduce()) return;
    const g = $(".glass", boardEl), t0 = performance.now();
    const id = setInterval(() => {
      if (performance.now() - t0 > ms) { clearInterval(id); return; }
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

  function prefixOf(boardEl) { return (boardEl.id || "").replace("-board", ""); }

  // ---- the climax: the board slowly spells I AM HERE
  async function prelude(prefix, opts) {
    const st = S[prefix];
    document.body.classList.add("climax");
    st.scene.classList.add("climax");
    st.audio = opts.audioUrl || null;
    st.letters = 0;
    sfx.drone(true);
    sfx.knock(); shake(st.scene);
    await wait(700);
    sfx.knock(); shake(st.scene);
    await wait(500);
    await say(prefix, "xochi", "Wait. The air just changed.", { tag: "Xochi keeps watch", hold: 500 });
    await say(prefix, "bigotes", "It is only a draft. Probably.", { tag: "Dr. Bigotes", hold: 500 });
    sfx.heart(true);
    st.speech.classList.add("hush");
    await wait(500);
  }

  // ---- the finale: lights out, the crew runs, the page moves on to The Room
  async function finale(prefix) {
    const st = S[prefix];
    st.cancelled = false;
    sfx.heart(false); sfx.drone(false);
    sfx.slam(); flash(); shake(st.scene);
    const dark = document.createElement("div");
    dark.className = "lights-out";
    document.body.append(dark);
    dark.addEventListener("animationend", () => dark.remove());
    $$(".seat", st.scene).forEach((s) => s.classList.add("scared"));
    await wait(900);
    sfx.whoosh();
    $$(".seat", st.scene).forEach((s) => { s.classList.remove("scared"); s.classList.add("run"); });
    const card = $("#act-card") || (() => {
      const c = document.createElement("div");
      c.id = "act-card"; c.className = "act"; c.hidden = true;
      c.innerHTML = '<div><p class="kicker">Case 3</p><h2>The Room</h2><p>The room you are sitting in right now.</p><button type="button" class="stay">Stay in the séance</button></div>';
      document.body.append(c);
      return c;
    })();
    const lines = [["luna", "Out! Everybody out!"], ["bigotes", "That was NOT the kettle!"], ["xochi", "Stay close to me!"]];
    const speaking = (async () => { for (const [w, t] of lines) await say(prefix, w, t, { tag: "", hold: 150, speed: 10 }); })();
    $(".stay", card).onclick = () => { st.cancelled = true; };
    await wait(1700);
    await speaking;
    if (reduce()) {
      $(".go", st.ctl).hidden = false;
      return;
    }
    card.hidden = false;
    card.classList.add("show");
    document.body.classList.add("act-on");
    await wait(2600);
    card.classList.remove("show");
    document.body.classList.remove("act-on");
    setTimeout(() => { card.hidden = true; }, 500);
    if (st.cancelled) {
      $$(".seat", st.scene).forEach((s) => s.classList.remove("run"));
      $(".go", st.ctl).hidden = false;
      return;
    }
    if (window.WHNav) window.WHNav.go("room");
    $(".go", st.ctl).hidden = false;
  }

  WH.stage = {
    open(prefix) {
      build(prefix);
      const st = S[prefix];
      if (!st) return;
      st.skip = false; st.cancelled = false; st.count = 0; st.quipped = new Set();
      $$(".seat", st.scene).forEach((s) => s.classList.remove("run", "scared"));
      $(".go", st.ctl).hidden = true;
      $(".skip", st.ctl).hidden = false;
      document.body.classList.add("seance-on");
      sfx.prime();
      st.root.scrollIntoView({ behavior: reduce() ? "auto" : "smooth", block: "start" });
    },
    close(prefix) {
      const st = S[prefix];
      if (!st) return;
      st.speech.classList.remove("hush");
      $(".skip", st.ctl).hidden = true;
      document.body.classList.remove("seance-on", "climax");
      st.scene.classList.remove("climax");
      $$(".seat", st.scene).forEach((s) => s.classList.remove("speaking"));
      sfx.heart(false); sfx.drone(false);
    },
    skipping(prefix) { return !!(S[prefix] && S[prefix].skip); },
    cancelled(prefix) { return !!(S[prefix] && S[prefix].cancelled); },

    async ask(prefix, question) {
      build(prefix);
      if (!S[prefix]) return;
      document.body.classList.add("seance-on");
      sfx.prime();
      await say(prefix, "luna", `“${question}”`, { tag: "Luna asks the board", hold: 300 });
    },
    async begin(prefix, r, opts) {
      build(prefix);
      const st = S[prefix];
      if (!st) return;
      $$(".seat", st.scene).forEach((s) => s.classList.add("lean"));
      if (opts.climax) await prelude(prefix, opts);
      else if (opts.finale) { st.scene.classList.remove("climax"); document.body.classList.remove("climax"); }
      else sfx.knock();
    },
    glass(boardEl, ch, slow) {
      trail(boardEl, slow ? 1400 : 650);
      light(boardEl, ch);
      sfx.tick();
    },
    letter(boardEl, ch, slow) {
      sfx.letter();
      if (!slow) return;
      const st = S[prefixOf(boardEl)];
      if (!st) return;
      shake(boardEl);
      st.letters += 1;
      if (st.letters === 4 && st.audio) {
        const a = new Audio(st.audio);
        a.volume = 0.95;
        a.play().catch(() => { /* autoplay blocked */ });
      }
    },
    async read(prefix, r, opts) {
      const st = S[prefix];
      if (!st) return;
      st.speech.classList.remove("hush");
      if (opts.finale) { await finale(prefix); return; }
      const ids = (r.grounding && r.grounding.related_evidence_ids) || [];
      const by = ($(`#${prefix}-seance .by`) || {}).textContent || "";
      const source = /template|scripted/i.test(by) ? "scripted reading" : /gemma/i.test(by) ? "written by Gemma 4" : by.trim().slice(0, 40);
      if (r.response.spoken) await say(prefix, "luna", `“${r.response.spoken}”`, { tag: `Luna reads the glass · ${source}`, hold: opts.climax ? 1400 : 700, speed: opts.climax ? 40 : 20 });
      const all = WH.evidenceFor(prefix);
      const e = ids.map((i) => all.find((x) => x.id === i)).find((x) => x && !st.quipped.has(x.id));
      if (opts.climax) {
        await say(prefix, "bigotes", "Two real sounds, both cited. And I have no kettle for this.", { tag: "Dr. Bigotes", hold: 900 });
      } else if (e) {
        st.quipped.add(e.id);
        await say(prefix, "bigotes", firstSentence(WH.bigotes(e, all)), { tag: `checks ${e.id} · ${e.start.toFixed(2)} s`, hold: 500 });
      }
      st.count += 1;
      const xochi = ["I kept watch. The glass moved by itself.", "Her words are gentle. Her warning is not.", "I will write it down: every answer cites a real moment."];
      if (!opts.climax && st.count % 3 === 1) await say(prefix, "xochi", xochi[(st.count - 1) / 3 % xochi.length | 0], { tag: "Xochi keeps watch", hold: 400 });
    },
    async end(prefix) {
      const st = S[prefix];
      if (!st) return;
      $$(".seat", st.scene).forEach((s) => s.classList.remove("lean", "speaking"));
    },
  };

  // build once now, so the crew is in place the moment the séance opens
  ["uh", "rm"].forEach(build);
})();
