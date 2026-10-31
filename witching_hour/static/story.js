/* Story mode: the whole investigation as a sequence of screens, one piece at a time, with Back and Next.
   It sits on top of the normal page: every stage lights up a few existing blocks (.st-on) and hides the rest,
   so the clip, the séance, the voices and the camera keep working exactly as they do in the full page.
   "Explore freely" switches back to the full page. Automated browsers (the tests, the tour recorder) get the full page. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const main = $("main");
  if (!main || !window.WHNav) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const UH = 'section[aria-label="PARANORMAL.exe, The Unheard"]';
  const RM = 'section[aria-label="PARANORMAL.exe, The Room"]';
  const UH_LEFT = `${UH} .layout > div:first-child`, UH_RIGHT = `${UH} .layout > div:last-child`;
  const sub = (k) => { const b = $(`.subtabs [data-sub="${k}"]`); if (b && !b.classList.contains("on")) b.click(); };
  const PARTS = ["Welcome", "The House", "The Unheard", "The Room", "How it was tested", "The end"];
  const FACE = { luna: "Luna, the Medium", bigotes: "Dr. Bigotes, the Skeptic", xochi: "Xochi, the Night Watch" };

  const STAGES = [
    { part: 0, view: "home", who: "luna", title: "What if someone tried to warn you, and you never heard them?",
      text: "Witching Hour is a ghost hunt for Halloween and Día de los Muertos. The evidence is real: sensor logs and recordings, measured by open models. The spirits are fiction, and nobody on the crew may say a word the evidence cannot back.",
      show: ["header.hero"], hide: ["header.hero > .tagline", "#crew", "header.hero nav.doors", "header.hero .start"] },
    { part: 0, view: "home", who: "xochi", title: "Meet the crew",
      text: "Three of us read the same evidence and never agree on what it means. Press play on a card to hear each of us.",
      show: ["#crew"], hide: ["header.hero > .kicker", "header.hero > h1", "header.hero > .hook", "header.hero > .tagline", "header.hero nav.doors", "header.hero .start"] },
    { part: 1, view: "house", who: "bigotes", title: "The haunting map",
      text: "Four months of a real house in Belgium, logged every ten minutes. Every square is one night. TabPFN learned what each room should read; the brighter the square, the further a room strayed from that. A blue dot means a room fell below 18 °C. Click a bright square to open that night.",
      enter: () => sub("nights"), show: ['section[aria-labelledby="map-title"]'], hide: ["#top-nights"] },
    { part: 1, view: "house", who: "luna", title: "One night, three voices",
      text: "I tell the night as a ghost story, Bigotes explains it, Xochi writes the note for the family. Each sentence cites the moment it comes from. At the bottom, call the spirit: the board spells its message, and I say what it means.",
      enter: () => { sub("nights"); if (!$("#night").children.length) $(".cell.l3, .cell.l2")?.click(); }, show: ["#night"], hide: [] },
    { part: 1, view: "house", who: "xochi", title: "Tonight",
      text: "The same spirit meter, pointed at tonight's weather: how would each room of that house feel? An illustration, not a promise.",
      enter: () => sub("tonight"), show: ["#tonight"], hide: [] },
    { part: 2, view: "unheard", who: "luna", title: "Kenji's case",
      text: "Kenji, a client in Japan, sent us his hallway camera's recording. That night his mother almost went out, then stopped at the door and stayed home. She never knew why. Your browser is reading the clip frame by frame while you watch.",
      extra: [["⏭ Skip the video, go to the séance", () => goTo(STAGES.findIndex((s) => s.id === "seance"))]],
      enter: () => { if (!$("#uh-evidence .event") && !$("#uh-demo").disabled) $("#uh-demo").click(); },
      show: [UH], hide: [`${UH} .term-actions`, "#uh-status", "#uh-timeline", `${UH} .key`, `${UH} h3.locker`, "#uh-evidence", UH_RIGHT] },
    { part: 2, view: "unheard", who: "bigotes", title: "What the camera really caught",
      text: "Five moments stood out from the rest of the clip. I wrote the most boring explanation I could find for each one. What I cannot explain, Luna takes to the board.",
      show: [UH], hide: [`${UH} .term-actions`, "#uh-status", "#uh-story", "#uh-video", UH_RIGHT] },
    { id: "seance", part: 2, view: "unheard", who: "luna", title: "The séance",
      text: "The spirit speaks only through the glass, three words at a time, and every answer must point at a real moment. This séance was recorded with Gemma 4 on a laptop. Watch the glass.",
      enter: seance,
      show: [UH], hide: [`${UH} > .term-body > .term-actions`, "#uh-status", "#uh-story", UH_LEFT, `${UH_RIGHT} > p.notice`, `${UH_RIGHT} > label.words`, `${UH_RIGHT} .receipts-slot`] },
    { part: 3, view: "room", who: "luna", title: "The Room: your turn",
      text: "Turn on your camera, or play without one. Summon the spirit of the room and pick a question. Then stay very still: if something really moves right after the glass stops, the game will notice. On this free demo the spirit is a template; at home, Gemma answers live.",
      show: [RM], hide: ["#rm-log"] },
    { part: 4, view: "lab", who: "bigotes", title: "How it was tested",
      text: "Of course I tested the meter. We planted fake ghosts in real nights and counted how many each detector caught. The receipts are counted from the repository, not typed by hand.",
      show: ["#archive", 'section[aria-labelledby="eval-title"]'], hide: ["#archive-body"] },
    { part: 4, view: "lab", who: "bigotes", title: "Which storyteller invents the least?",
      text: "Four open models through Backboard, the same nights and the same rule: every number must match the evidence it cites. And what is in the kit.",
      show: ["#bakeoff-sec", "section.how"], hide: [] },
    { part: 5, view: "home", who: "xochi", title: "Case closed",
      text: "I kept watch. Here is what I saw.", show: ["#st-end"], hide: [] },
  ];

  // ---- the pieces story mode adds to the page
  const intro = document.createElement("div");
  intro.className = "st-intro st-on";
  main.prepend(intro);
  const end = document.createElement("section");
  end.id = "st-end";
  end.innerHTML = `<div class="crew-row"><img src="/static/characters/luna.svg" alt="Luna"><img src="/static/characters/bigotes.svg" alt="Dr. Bigotes"><img src="/static/characters/xochi.svg" alt="Xochi"></div>
    <h2>The evidence is real. The spirits are fiction.</h2><p>And the feeling is yours. Every number you saw came from a measurement, an open model or a saved file in the repository.</p>
    <div class="row"><button type="button" class="big st-again">↺ Start again</button><button type="button" class="big alt st-free">Explore everything freely</button>
    <a class="big alt" href="https://github.com/jenniferevangelista-de/witching-hour">The code on GitHub</a></div>`;
  main.insertBefore(end, $("footer.ofrenda"));
  const bar = document.createElement("nav");
  bar.className = "st-bar";
  bar.setAttribute("aria-label", "Story progress");
  bar.innerHTML = `<button type="button" class="big alt back">← Back</button>
    <div class="mid"><div class="where"></div><div class="parts">${PARTS.map((p, i) => `<button type="button" data-p="${i}">${p}</button>`).join("")}</div></div>
    <button type="button" class="big next">Next →</button>`;
  document.body.append(bar);
  const explore = document.createElement("button");
  explore.type = "button";
  explore.className = "big alt st-explore";
  explore.textContent = "Explore freely";
  document.body.append(explore);
  const back = document.createElement("button");
  back.type = "button";
  back.className = "big st-story-back";
  back.textContent = "▶ Story mode";
  document.body.append(back);

  const KEY = "wh_story_stage", MODE = "wh_mode";
  const store = { get(k) { try { return sessionStorage.getItem(k); } catch (_) { return null; } }, set(k, v) { try { sessionStorage.setItem(k, v); } catch (_) { /* private mode */ } } };
  let at = -1, timers = [], watcher = null;

  function clearStage() {
    timers.forEach(clearTimeout); timers = [];
    if (watcher) { watcher.disconnect(); watcher = null; }
    $$(".st-on").forEach((el) => { if (el !== intro) el.classList.remove("st-on"); });
    $$(".st-hide").forEach((el) => el.classList.remove("st-hide"));
  }
  function light(sel) {
    $$(sel).forEach((el) => {
      for (let n = el; n && n !== main; n = n.parentElement) n.classList.add("st-on");
    });
  }

  function goTo(i) {
    const s = STAGES[i];
    if (!s) return;
    store.set(KEY, String(i));
    if ((document.body.dataset.view || "home") !== s.view) {
      window.WHNav.go(s.view);   // a played page reloads here; the stage is already saved and resumes below
      if (window.WH && window.WH.dirty && window.WH.dirty()) return;
    }
    clearStage();
    at = i;
    if (s.enter) s.enter();
    s.show.forEach(light);
    s.hide.forEach((q) => $$(q).forEach((el) => el.classList.add("st-hide")));
    intro.innerHTML = `<img src="/static/characters/${s.who}.svg" alt="${FACE[s.who]}"><div><div class="kick">Part ${s.part + 1} · ${PARTS[s.part]}</div><h2>${s.title}</h2><p>${s.text}</p>${s.extra ? '<div class="st-extra"></div>' : ""}</div>`;
    (s.extra || []).forEach(([label, fn]) => { const b = document.createElement("button"); b.type = "button"; b.className = "big alt"; b.textContent = label; b.onclick = fn; intro.querySelector(".st-extra").append(b); });
    bar.querySelector(".where").innerHTML = `${PARTS[s.part]} <small>· ${s.title} · ${i + 1} of ${STAGES.length}</small>`;
    bar.querySelectorAll(".parts button").forEach((b) => { const p = +b.dataset.p; b.classList.toggle("on", p === s.part); b.classList.toggle("done", p < s.part); });
    bar.querySelector(".back").disabled = i === 0;
    bar.querySelector(".next").hidden = i === STAGES.length - 1;
    bar.querySelector(".next").textContent = i === 0 ? "Begin →" : "Next →";
    scrollTo({ top: 0, behavior: "auto" });
    requestAnimationFrame(() => dispatchEvent(new Event("resize")));
  }
  const next = () => goTo(Math.min(at + 1, STAGES.length - 1));
  const prev = () => goTo(Math.max(at - 1, 0));

  // ---- The House: a click on a night moves the story on to that night
  document.addEventListener("click", (e) => {
    if (!document.body.classList.contains("story") || at < 0) return;
    if (STAGES[at].title === "The haunting map" && e.target.closest(".cell[data-night]") && !e.target.closest(".legend")) {
      timers.push(setTimeout(next, 350));
    }
  });

  // ---- the séance: summon, replay, and when the board says I AM HERE the glass breaks and the story moves on
  function seance() {
    const t0 = Date.now();
    if (!$("#uh-evidence .event") && !$("#uh-demo").disabled) $("#uh-demo").click();   // skipped straight here: start reading the clip
    const step = () => {
      if (at < 0 || STAGES[at].id !== "seance") return;
      const note = intro.querySelector(".st-wait") || intro.querySelector("p").appendChild(Object.assign(document.createElement("b"), { className: "st-wait" }));
      const reading = /Reading frames/.test($("#uh-status").textContent);
      note.textContent = reading ? ` (${$("#uh-status").textContent.replace("Reading frames...", "Luna is still reading the clip:")})` : "";
      const replay = $("#uh-replay"), open = $("#uh-open");
      if (replay && !replay.hidden && !replay.classList.contains("off")) { replay.click(); return watchClimax(); }
      if (open && !open.hidden && !open.disabled && !$("#uh-seance:not([hidden])")) open.click();
      if (Date.now() - t0 < 90000) timers.push(setTimeout(step, 800));
    };
    timers.push(setTimeout(step, 600));
  }
  function watchClimax() {
    const spelled = $("#uh-spelled");
    if (!spelled) return;
    let fired = false;
    watcher = new MutationObserver(() => {
      if (fired || spelled.textContent.replace(/\s+/g, " ").trim() !== "I AM HERE") return;
      fired = true;
      timers.push(setTimeout(shatter, 5200));   // let the Guardian finish "I will never leave you"
    });
    watcher.observe(spelled, { childList: true, characterData: true, subtree: true });
  }
  function shatter() {
    const glass = $("#uh-board .glass");
    if (glass) {
      const r = glass.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      glass.classList.add("shatter");
      if (!reduce) for (let k = 0; k < 18; k++) {
        const s = document.createElement("i");
        s.className = "shard";
        const a = Math.random() * Math.PI * 2, d = 120 + Math.random() * 260;
        Object.assign(s.style, { left: `${cx}px`, top: `${cy}px`, "--dx": `${Math.cos(a) * d}px`, "--dy": `${Math.sin(a) * d}px`, "--r": `${Math.random() * 720 - 360}deg` });
        document.body.append(s);
        setTimeout(() => s.remove(), 1300);
      }
    }
    const f = document.createElement("div");
    f.className = "flash";
    document.body.append(f);
    setTimeout(() => f.remove(), 800);
    breakSound();
    timers.push(setTimeout(next, 1700));
  }
  function breakSound() {
    try {
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      const t = ac.currentTime, n = ac.sampleRate * 0.9, buf = ac.createBuffer(1, n, ac.sampleRate), d = buf.getChannelData(0);
      for (let k = 0; k < n; k++) d[k] = (Math.random() * 2 - 1) * Math.pow(1 - k / n, 4);
      const src = ac.createBufferSource(), hp = ac.createBiquadFilter(), g = ac.createGain();
      src.buffer = buf; hp.type = "highpass"; hp.frequency.value = 1800; g.gain.value = 0.7;
      src.connect(hp).connect(g).connect(ac.destination); src.start(t);
      for (let k = 0; k < 7; k++) {   // the bright tinkle of pieces landing
        const o = ac.createOscillator(), og = ac.createGain(), at2 = t + 0.05 + Math.random() * 0.5;
        o.type = "sine"; o.frequency.value = 2600 + Math.random() * 3800;
        og.gain.setValueAtTime(0.0001, at2); og.gain.exponentialRampToValueAtTime(0.18, at2 + 0.005); og.gain.exponentialRampToValueAtTime(0.0001, at2 + 0.25);
        o.connect(og).connect(ac.destination); o.start(at2); o.stop(at2 + 0.3);
      }
      setTimeout(() => ac.close(), 1500);
    } catch (_) { /* no audio */ }
  }

  // ---- controls
  bar.querySelector(".next").addEventListener("click", next);
  bar.querySelector(".back").addEventListener("click", prev);
  bar.querySelectorAll(".parts button").forEach((b) => b.addEventListener("click", () => goTo(STAGES.findIndex((s) => s.part === +b.dataset.p))));
  end.querySelector(".st-again").addEventListener("click", () => goTo(0));
  function freeMode() {
    store.set(MODE, "explore");
    clearStage();
    document.body.classList.remove("story");
    window.WHNav.go(STAGES[Math.max(at, 0)].view === "home" ? "home" : STAGES[Math.max(at, 0)].view);
    dispatchEvent(new Event("scroll"));
  }
  explore.addEventListener("click", freeMode);
  end.querySelector(".st-free").addEventListener("click", freeMode);
  back.addEventListener("click", () => { store.set(MODE, "story"); document.body.classList.add("story"); goTo(Math.max(at, 0)); });
  document.addEventListener("keydown", (e) => {
    if (!document.body.classList.contains("story") || e.target.closest("input, textarea, select, [contenteditable]")) return;
    if (e.key === "ArrowRight") next();
    else if (e.key === "ArrowLeft") prev();
  });

  // ---- start
  const forced = /[?&]story\b/.test(location.search);
  const free = /[?&]explore\b/.test(location.search) || store.get(MODE) === "explore" || navigator.webdriver;
  if (free && !forced) return;
  document.body.classList.add("story");
  const saved = +store.get(KEY);
  const fromHash = { house: 2, unheard: 5, room: 8, lab: 9 }[(location.hash || "").slice(1)];
  goTo(Number.isFinite(saved) && STAGES[saved] && store.get(KEY) !== null ? saved : fromHash ?? 0);
})();
