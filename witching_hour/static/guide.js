/* A step rail beside each case, a "more below" pill, and a guided tour across the whole investigation.
   Loaded after nav.js. It only reads the page and scrolls; it never presses a button that plays something,
   so the visitor stays in charge of the clip, the séance and the camera. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const sub = (k) => () => { const b = $(`.subtabs [data-sub="${k}"]`); if (b && !b.classList.contains("on")) b.click(); };

  // what each case asks of the visitor, in order; the first selector that is on screen wins
  const STEPS = {
    house: [
      { label: "The haunting map", sel: ['section[aria-labelledby="map-title"]'], before: sub("nights") },
      { label: "A night's case file", sel: ["#night"], before: sub("nights") },
      { label: "Tonight", sel: ["#tonight"], before: sub("tonight") },
      { label: "Ask the crew", sel: ["section.ask"], before: sub("ask") },
    ],
    unheard: [
      { label: "Open the case", sel: ["#uh-demo"] },
      { label: "Watch the clip", sel: ["#uh-video"] },
      { label: "Read the evidence", sel: ["#uh-evidence .event", "#uh-evidence"] },
      { label: "Check the receipts", sel: [".receipts-slot"] },
      { label: "Summon the spirit", sel: ["#uh-open:not([hidden])", "#uh-words"] },
      { label: "The séance", sel: ["#uh-stage", "#uh-seance-slot"] },
      { label: "Xochi's dossier", sel: ["#uh-dossier"] },
    ],
    room: [
      { label: "Camera, or no camera", sel: ["#rm-start"] },
      { label: "Summon the room's spirit", sel: ["#rm-seance-open:not([hidden])", "#rm-status"] },
      { label: "Ask, then stay still", sel: ["#rm-stage", "#rm-seance-slot"] },
    ],
    lab: [
      { label: "The crew's archive", sel: ["#archive"] },
      { label: "Planted ghosts", sel: ['section[aria-labelledby="eval-title"]'] },
      { label: "The model bake-off", sel: ["#bakeoff-sec"] },
      { label: "How it works", sel: ["section.how"] },
    ],
  };
  const NEXT_CASE = { house: "room", unheard: "house", room: "lab" };
  const LABEL = { house: "The House", unheard: "The Unheard", room: "The Room", lab: "How it was tested" };

  const shown = (el) => !!el && !el.hidden && el.getClientRects().length > 0 && !el.closest(".view-off, .sub-off, [hidden]");
  const target = (step) => step.sel.map((s) => $(s)).find(shown) || null;
  const view = () => document.body.dataset.view || "home";

  function scrollToEl(el) {
    const top = el.getBoundingClientRect().top + scrollY - 110;
    scrollTo({ top: Math.max(0, top), behavior: reduce ? "auto" : "smooth" });
  }
  function go(step) {
    if (step.before) step.before();
    requestAnimationFrame(() => { const el = target(step); if (el) scrollToEl(el); });
  }

  // ---- the rail
  const rail = document.createElement("nav");
  rail.className = "rail";
  rail.setAttribute("aria-label", "Steps in this case");
  document.body.append(rail);
  const pill = document.createElement("button");
  pill.type = "button";
  pill.className = "more-below";
  pill.hidden = true;
  document.body.append(pill);

  let steps = [], now = -1, built = null;
  function build() {
    const v = view();
    steps = STEPS[v] || [];
    document.body.classList.toggle("has-rail", steps.length > 0);
    built = v;
    now = -1;
    if (!steps.length) { rail.innerHTML = ""; pill.hidden = true; return; }
    rail.innerHTML = `<h4>${LABEL[v]}</h4><ol>${steps.map((s, i) => `<li data-i="${i}"><button type="button">${s.label}</button></li>`).join("")}</ol>` +
      '<button type="button" class="big alt rail-tour">🧭 Guided tour</button>';
    rail.querySelectorAll("li button").forEach((b) => b.addEventListener("click", () => go(steps[+b.parentElement.dataset.i])));
    rail.querySelector(".rail-tour").addEventListener("click", () => startTour(firstTourStepFor(v)));
    spy();
  }

  // the current step is the last one whose top has passed the upper third of the screen
  function spy() {
    if (built !== view()) { build(); return; }
    if (!steps.length) return;
    const line = innerHeight * 0.38;
    let cur = 0;
    steps.forEach((s, i) => { const el = target(s); if (el && el.getBoundingClientRect().top < line) cur = i; });
    if (cur !== now) {
      now = cur;
      rail.querySelectorAll("li").forEach((li, i) => { li.classList.toggle("done", i < cur); li.classList.toggle("now", i === cur); });
    }
    // the pill points at what comes next: the next step below, or the next case at the end of this one
    const nextStep = steps.slice(cur + 1).find((s) => { const el = target(s); return el && el.getBoundingClientRect().top > innerHeight * 0.6; });
    const atEnd = innerHeight + scrollY >= document.documentElement.scrollHeight - 40;
    if (nextStep) {
      pill.innerHTML = `<span class="arrow">↓</span> More below <small>· ${nextStep.label}</small>`;
      pill.onclick = () => go(nextStep);
      pill.hidden = false;
    } else if (atEnd && NEXT_CASE[view()]) {
      const k = NEXT_CASE[view()];
      pill.innerHTML = `Next case <small>· ${LABEL[k]}</small> <span>→</span>`;
      pill.onclick = () => window.WHNav && window.WHNav.go(k);
      pill.hidden = false;
    } else pill.hidden = true;
  }
  let ticking = false;
  const onScroll = () => { if (ticking) return; ticking = true; requestAnimationFrame(() => { ticking = false; spy(); }); };
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", onScroll);
  addEventListener("hashchange", () => setTimeout(spy, 60));
  addEventListener("popstate", () => setTimeout(spy, 60));
  document.addEventListener("click", () => setTimeout(spy, 80));
  new MutationObserver(onScroll).observe(document.querySelector("main"), { attributes: true, attributeFilter: ["hidden", "class"], subtree: true, childList: true });

  // ---- the guided tour: Luna walks you through the whole flow, one highlighted thing at a time
  const TOUR = [
    { view: "home", sel: ["#start-here"], text: "Start here. The Warning is a staged 20-second hallway clip. Your browser measures it, then the crew argues about what it means." },
    { view: "home", sel: ["nav.topbar"], text: "Three cases and a lab. This menu stays at the top, and the steps of each case follow you on the left." },
    { view: "unheard", sel: ["#uh-demo"], text: "Case two first, because it is the shortest. Press Open the case: the browser reads the clip frame by frame, which takes about 20 seconds." },
    { view: "unheard", sel: ["#uh-timeline", "#uh-video"], text: "Light, motion and sound over time. The shaded bands are the moments that stood out from the rest of the clip." },
    { view: "unheard", sel: ["#uh-evidence .event", "#uh-evidence"], text: "The evidence locker: each moment is measured, and Dr. Bigotes writes the most boring explanation he can find." },
    { view: "unheard", sel: [".receipts-slot"], text: "The receipts are counted from the repository, not typed by hand." },
    { view: "unheard", sel: ["#uh-open:not([hidden])", "#uh-words"], text: "For what Bigotes could not explain, summon the spirit. The recorded séance replays a run made with Gemma 4 on a laptop. The spirit is fiction; every answer must cite a real moment." },
    { view: "unheard", sel: ["#uh-dossier"], text: "Xochi's dossier keeps what was measured and what the board said in separate sections." },
    { view: "house", sel: ['section[aria-labelledby="map-title"]'], before: sub("nights"), text: "The House: four months of a real house. Every square is a night; the bright ones broke the pattern TabPFN expected. Click one." },
    { view: "house", sel: ["#night"], before: sub("nights"), text: "A case file: Luna, Bigotes and Xochi tell the same night. Hover a citation to see the moment it points at." },
    { view: "room", sel: ["#rm-start"], text: "The Room is your turn. Use your camera, or play without one. Nothing is recorded; only measured moments reach the board." },
    { view: "lab", sel: ['section[aria-labelledby="eval-title"]', "#archive"], text: "And how it was tested: planted ghosts, the model bake-off and a fine-tuned apprentice, with their limits written down." },
  ];
  const KEY = "wh_tour_step";
  const firstTourStepFor = (v) => Math.max(0, TOUR.findIndex((t) => t.view === v));
  let spot = null, tip = null, at = -1;

  function stopTour() {
    at = -1;
    try { sessionStorage.removeItem(KEY); } catch (_) { /* private mode */ }
    spot?.remove(); tip?.remove(); spot = tip = null;
    document.body.classList.remove("touring");
    removeEventListener("resize", place);
    removeEventListener("scroll", place);
  }
  function place() {
    if (at < 0 || !spot || !tip) return;
    const el = TOUR[at].sel.map((s) => $(s)).find(shown);
    if (!el) { spot.style.display = "none"; tip.style.left = "50%"; tip.style.top = "50%"; tip.style.transform = "translate(-50%, -50%)"; return; }
    const r = el.getBoundingClientRect(), pad = 8;
    spot.style.display = "block";
    Object.assign(spot.style, { top: `${r.top + scrollY - pad}px`, left: `${r.left + scrollX - pad}px`, width: `${r.width + pad * 2}px`, height: `${Math.min(r.height, innerHeight * 0.7) + pad * 2}px` });
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    const below = r.top + Math.min(r.height, innerHeight * 0.7) + 18;
    const top = below + th < innerHeight - 10 ? below : Math.max(80, r.top - th - 18);
    const left = Math.min(Math.max(16, r.left), innerWidth - tw - 16);
    Object.assign(tip.style, { top: `${top}px`, left: `${left}px`, transform: "none" });
  }
  function showStep(i) {
    const t = TOUR[i];
    if (!t) { stopTour(); return; }
    at = i;
    try { sessionStorage.setItem(KEY, String(i)); } catch (_) { /* private mode */ }
    if (view() !== t.view && window.WHNav) window.WHNav.go(t.view);   // may reload a played page; the step survives in sessionStorage
    if (t.before) t.before();
    document.body.classList.add("touring");
    if (!spot) { spot = document.createElement("div"); spot.className = "tour-spot"; document.body.append(spot); }
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "tour-tip";
      tip.setAttribute("role", "dialog");
      tip.setAttribute("aria-label", "Guided tour");
      tip.tabIndex = -1;
      document.body.append(tip);
      addEventListener("resize", place);
      addEventListener("scroll", place, { passive: true });
    }
    tip.innerHTML = `<div class="who"><img src="/static/characters/luna.svg" alt=""><div><b>Luna</b><br><span>your guide tonight</span></div></div>
      <p>${t.text}</p>
      <div class="row"><span class="count">${i + 1} of ${TOUR.length}</span>
      <button type="button" class="skip">End tour</button>${i ? '<button type="button" class="back">Back</button>' : ""}
      <button type="button" class="next">${i === TOUR.length - 1 ? "Finish" : "Next"}</button></div>`;
    tip.querySelector(".next").onclick = () => showStep(i + 1);
    tip.querySelector(".skip").onclick = stopTour;
    const back = tip.querySelector(".back");
    if (back) back.onclick = () => showStep(i - 1);
    setTimeout(() => {
      const el = t.sel.map((s) => $(s)).find(shown);
      if (el) scrollToEl(el);
      setTimeout(place, reduce ? 0 : 450);
      place();
      tip.focus({ preventScroll: true });
    }, 120);
  }
  function startTour(i = 0) { showStep(i); }
  document.addEventListener("keydown", (e) => {
    if (at < 0) return;
    if (e.key === "Escape") stopTour();
    else if (e.key === "ArrowRight") showStep(at + 1);
    else if (e.key === "ArrowLeft" && at > 0) showStep(at - 1);
  });

  // a tour button on the home page and in the top bar
  const startRow = $(".start");
  if (startRow) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "big alt tour-btn";
    b.textContent = "🧭 Take the guided tour";
    b.addEventListener("click", () => startTour(0));
    startRow.querySelector("#start-here")?.after(b);
  }
  const bar = $("nav.topbar");
  if (bar) {
    const a = document.createElement("a");
    a.href = "#tour";
    a.className = "tour-link";
    a.innerHTML = '<span aria-hidden="true">🧭</span><span class="full">Guided tour</span><span class="short">Tour</span>';
    a.addEventListener("click", (e) => { e.preventDefault(); startTour(firstTourStepFor(view()) || 0); });
    bar.append(a);
  }

  build();
  // a tour that crossed a page reload picks up where it was
  let resume = null;
  try { resume = sessionStorage.getItem(KEY); } catch (_) { /* private mode */ }
  if (resume !== null && TOUR[+resume]) setTimeout(() => showStep(+resume), 400);
})();
