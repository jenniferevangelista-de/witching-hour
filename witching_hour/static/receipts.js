/* Receipts: numbers counted from the repository (demo/make_receipts.py), shown next to the evidence. */
(() => {
  "use strict";
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (x) => `${Math.round(x * 100)}%`;
  function html(r) {
    const best = r.planted.find((p) => p.backend.startsWith("tabpfn")) || r.planted[0];
    const others = r.planted.filter((p) => p !== best).map((p) => `${esc(p.backend)} ${pct(p.recall_fpr5)}`).join(", ");
    const models = r.bakeoff.length ? `${r.bakeoff.length} saved model runs; ${pct(Math.min(...r.bakeoff.map((m) => m.grounded)))} to ${pct(Math.max(...r.bakeoff.map((m) => m.grounded)))} passed reference and number checks, not explanation checks` : "";
    const item = (n, t, s) => `<li><b>${esc(n)}</b><span>${esc(t)}</span><small>${esc(s)}</small></li>`;
    return `<h3>🧾 Receipts <small>counted from the repository on ${esc(r.counted_at)}</small></h3>
      <ul class="rc">
        ${item(r.warning.moments, "moments measured in The Warning", `${r.warning.cited.length} of them cited by the recorded séance: ${r.warning.all_cited_exist ? "every citation points at a real moment" : "CHECK: a citation points nowhere"}`)}
        ${item(r.tests, "tests in the saved repository snapshot", `${r.workflows} workflows; see the latest GitHub Actions run for execution results`)}
        ${item(pct(best.recall_fpr5), "of planted anomalies caught by TabPFN", `${best.cases} exploratory cases; threshold set on the same nights to target 5% false alarms. Baselines: ${others}`)}
        ${item(r.nights, "nights scanned", `${r.stories} stories written, each checked sentence by sentence`)}
        ${item(r.voice_lines, "voice lines recorded", "the crew and the Guardian, recorded once, so the demo needs no key")}
        ${models ? item(r.bakeoff.length, "open models in the bake-off", models) : ""}
      </ul>
      <p class="notice">A recorded repository snapshot, counted from saved files. The model comparison uses different retry protocols; reference checks do not prove a supernatural explanation.</p>`;
  }
  async function load() {
    const slots = document.querySelectorAll(".receipts-slot");
    if (!slots.length) return;
    try {
      const r = await (await fetch("/api/extra/receipts")).json();
      if (!r || !r.tests) return;
      slots.forEach((s) => { s.innerHTML = html(r); s.hidden = false; });
    } catch (_) { /* optional */ }
  }
  load();
})();
