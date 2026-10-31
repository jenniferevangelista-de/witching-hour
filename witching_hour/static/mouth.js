/* Talking faces: while a character talks (.speaking in the séance, .talking on the first screen),
   Xochi and Dr. Bigotes open the very mouth they are drawn with, and Luna's crystal ball pulses.
   Each picture is wrapped in a .face that carries its float, with an overlay drawn in the same 240×260 space. */
(() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  // the overlay for each character, in the drawings' own coordinates
  const PARTS = {
    // Xochi's open smile with her tongue, the same shape as the drawing, opening downwards from the top lip
    xochi: '<g class="jaw" style="transform-origin:120px 137px"><path d="M106 137 Q120 151 134 137 Z" fill="#2a2048" stroke="#2a2048" stroke-width="3" stroke-linejoin="round"/><path d="M114 144 Q120 154 126 144 Z" fill="#ff7a9a"/></g>',
    // Dr. Bigotes's cat mouth opens into a small dark "o" under the same whiskered line
    bigotes: '<g class="jaw" style="transform-origin:120px 134px"><path d="M111 134 Q120 147 129 134 Q120 137 111 134 Z" fill="#2a2048"/><path d="M115 139 Q120 145 125 139 Z" fill="#ff7a9a"/></g>',
    // Luna does not talk with a mouth: her crystal ball glows with her voice
    luna: '<defs><radialGradient id="ballpulse"><stop offset="0" stop-color="#e6d4ff" stop-opacity=".95"/><stop offset=".55" stop-color="#a77bff" stop-opacity=".55"/><stop offset="1" stop-color="#a77bff" stop-opacity="0"/></radialGradient></defs><circle class="ball" cx="120" cy="196" r="34" fill="url(#ballpulse)"/>',
  };
  const COPY = ["animationName", "animationDuration", "animationDelay", "animationIterationCount", "animationTimingFunction", "maxWidth"];

  function wrap(img) {
    if (img.parentElement && img.parentElement.classList.contains("face")) return;
    const who = ((img.getAttribute("src") || "").match(/characters\/(\w+)\.svg/) || [])[1];
    if (!PARTS[who]) return;
    const cs = getComputedStyle(img);
    const face = document.createElement("span");
    face.className = `face ${who}`;
    COPY.forEach((k) => { face.style[k] = cs[k]; });
    img.replaceWith(face);
    face.append(img);
    Object.assign(img.style, { animation: "none", maxWidth: "none" });
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 240 260");
    svg.setAttribute("class", "talk-layer");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML = PARTS[who];
    face.append(svg);
  }
  const scan = () => document.querySelectorAll(".seat > img, .st-cast figure > img").forEach(wrap);
  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
  scan();
})();
