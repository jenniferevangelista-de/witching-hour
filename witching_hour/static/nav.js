/* Navigation for Witching Hour: one case at a time instead of one very long page.
   Routes are plain hashes (#home, #house, #unheard, #room, #lab), so the back button and shared links work.
   A date such as #2016-04-19 (set by app.js when a night opens) belongs to The House.
   Without this script the page still works as a single long page. */
(() => {
  const VIEWS = {
    home: { icon: "🕯️", label: "Home", short: "Home", title: "Witching Hour",
      sel: ["header.hero"] },
    house: { icon: "🏚️", label: "The House", short: "House", title: "The House",
      sel: ["#case-house", ".subtabs", 'section[aria-labelledby="map-title"]', "#tonight", "#night", "section.ask"] },
    unheard: { icon: "🎞️", label: "The Unheard", short: "Unheard", title: "The Unheard",
      sel: ["#unheard", 'section[aria-label="PARANORMAL.exe, The Unheard"]', "#uh-steps"] },
    room: { icon: "📹", label: "The Room", short: "Room", title: "The Room",
      sel: ["#room", 'section[aria-label="PARANORMAL.exe, The Room"]'] },
    lab: { icon: "🧪", label: "How it was tested", short: "Tests", title: "How it was tested",
      sel: ["#archive", 'section[aria-labelledby="eval-title"]', "#bakeoff-sec", "section.how"] },
  };
  const ORDER = ["home", "house", "unheard", "room", "lab"];
  const DATE = /^\d{4}-\d{2}-\d{2}$/;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const main = document.querySelector("main");
  if (!main) return;

  const parse = (hash) => {
    const h = decodeURIComponent((hash || "").replace(/^#/, ""));
    if (VIEWS[h]) return h;
    if (h === "case-house" || DATE.test(h)) return "house";
    if (h === "evidence" || h === "method") return "lab";
    return "home";
  };

  // ---- slow fog behind everything
  ["", "two"].forEach((c) => { const f = document.createElement("div"); f.className = `fog ${c}`.trim(); f.setAttribute("aria-hidden", "true"); document.body.insertBefore(f, main); });

  // ---- top bar
  const bar = document.createElement("nav");
  bar.className = "topbar";
  bar.setAttribute("aria-label", "Witching Hour");
  bar.innerHTML = ORDER.map((k) => {
    const v = VIEWS[k];
    return `<a href="#${k}" data-go="${k}"><span aria-hidden="true">${v.icon}</span><span class="full">${v.label}</span><span class="short">${v.short}</span></a>`;
  }).join("");
  document.body.insertBefore(bar, main);

  // ---- home: a clear way in, the three doors before the crew
  const hero = document.querySelector("header.hero");
  if (hero) {
    const doors = hero.querySelector("nav.doors");
    const crew = hero.querySelector("#crew");
    const tag = hero.querySelector(".tagline");
    if (doors) {
      doors.querySelectorAll("a.door").forEach((a) => {
        const h = a.getAttribute("href");
        a.setAttribute("href", h === "#case-house" ? "#house" : h);
        a.dataset.go = parse(a.getAttribute("href"));
      });
      if (crew) hero.insertBefore(doors, crew);
    }
    const start = document.createElement("div");
    start.className = "start";
    start.innerHTML = '<button type="button" class="big start-btn" id="start-here">▶ Start here: open <i>The Warning</i></button>' +
      '<span class="start-note">A staged 20-second hallway clip. Your browser measures it, then the crew argues about what it means.</span>';
    if (tag) tag.after(start);
  }

  // ---- The Unheard: three steps so the story has a path
  const uh = document.querySelector("#unheard");
  if (uh) {
    const steps = document.createElement("ol");
    steps.className = "steps";
    steps.id = "uh-steps";
    steps.innerHTML = '<li data-s="1">Watch the clip</li><li data-s="2">Read the evidence</li><li data-s="3">Hear the séance</li>';
    uh.after(steps);
  }
  const setStep = (n) => {
    document.querySelectorAll("#uh-steps li").forEach((li) => {
      const s = +li.dataset.s;
      li.classList.toggle("done", s < n);
      li.classList.toggle("now", s === n);
    });
  };
  setStep(1);
  document.addEventListener("click", (e) => {
    const id = e.target.closest("button, label")?.id || "";
    if (id === "uh-demo") setStep(2);
    else if (id === "uh-replay" || id === "uh-open" || id === "uh-dossier") setStep(3);
  });
  document.getElementById("uh-file")?.addEventListener("change", () => setStep(2));

  // ---- pager at the end of each view
  const pager = document.createElement("div");
  pager.className = "pager";
  const foot = document.querySelector("footer.ofrenda");
  if (foot) main.insertBefore(pager, foot); else main.append(pager);

  // ---- The House has three parts, shown one at a time
  const SUB = {
    nights: { label: "🗺️ The nights", sel: ['section[aria-labelledby="map-title"]', "#night"] },
    tonight: { label: "🕯️ Tonight", sel: ["#tonight"] },
    ask: { label: "🔮 Ask the crew", sel: ["section.ask"] },
  };
  let sub = "nights";
  const subbar = document.createElement("div");
  subbar.className = "subtabs";
  subbar.setAttribute("role", "tablist");
  subbar.innerHTML = Object.entries(SUB).map(([k, v]) => `<button type="button" role="tab" data-sub="${k}">${v.label}</button>`).join("");
  document.querySelector("#case-house")?.after(subbar);
  function applySub() {
    Object.entries(SUB).forEach(([k, v]) => v.sel.forEach((q) => document.querySelectorAll(q).forEach((el) => el.classList.toggle("sub-off", k !== sub))));
    subbar.querySelectorAll("button").forEach((b) => { const on = b.dataset.sub === sub; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
  }
  subbar.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-sub]");
    if (!b) return;
    sub = b.dataset.sub;
    applySub();
  });
  applySub();

  // ---- switching views
  let current = null;
  const visible = (k) => VIEWS[k].sel.flatMap((s) => [...document.querySelectorAll(s)]);

  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  function show(k, { scroll = true } = {}) {
    if (k === current) return;
    // something was played or is still talking: reload on the new page, so nothing keeps speaking and every page starts from zero
    if (current && window.WH && window.WH.dirty && window.WH.dirty()) { location.reload(); return; }
    current = k;
    const keep = new Set(visible(k));
    ORDER.forEach((name) => visible(name).forEach((el) => { if (!keep.has(el)) el.classList.add("view-off"); }));
    keep.forEach((el) => {
      el.classList.remove("view-off");
      if (!reduce) { el.classList.remove("view-in"); void el.offsetWidth; el.classList.add("view-in"); }
    });
    bar.querySelectorAll("a").forEach((a) => {
      const on = a.dataset.go === k;
      a.classList.toggle("on", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    document.title = k === "home" ? "Witching Hour" : `${VIEWS[k].title} · Witching Hour`;
    document.body.dataset.view = k;

    const i = ORDER.indexOf(k), prev = ORDER[i - 1], next = ORDER[i + 1];
    pager.innerHTML =
      (prev ? `<a class="big alt" href="#${prev}" data-go="${prev}">← ${VIEWS[prev].label}</a>` : "<span></span>") +
      (next ? `<a class="big" href="#${next}" data-go="${next}">${VIEWS[next].label} →</a>` : "<span></span>");
    pager.hidden = k === "home";
    // "How it was tested" blinks in the menu on every page after the first
    bar.querySelector('a[data-go="lab"]').classList.toggle("blink", k !== "home" && k !== "lab");

    // the timeline canvas measures its width when drawn, so redraw once it is visible again
    requestAnimationFrame(() => dispatchEvent(new Event("resize")));
    if (scroll) scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    const h = visible(k).map((el) => el.querySelector("h1, h2"))[0];
    if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
  }

  function route() {
    show(parse(location.hash));
  }

  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-go]");
    if (!a) return;
    e.preventDefault();
    const k = a.dataset.go;
    if (location.hash !== `#${k}`) history.pushState(null, "", `#${k}`);
    show(k);
  });

  document.getElementById("start-here")?.addEventListener("click", () => {
    history.pushState(null, "", "#unheard");
    show("unheard");
    setTimeout(() => document.getElementById("uh-demo")?.click(), 150);
  });

  window.WHNav = { go(k) { if (VIEWS[k]) { if (location.hash !== `#${k}`) history.pushState(null, "", `#${k}`); show(k); } } };

  addEventListener("popstate", route);
  addEventListener("hashchange", route);
  show(parse(location.hash), { scroll: false });
})();
