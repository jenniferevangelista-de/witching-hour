/* Moving mouths: while a character talks (.speaking in the séance, .talking on the first screen),
   an open mouth flaps over their drawn smile. Each picture is wrapped in a .face that carries its float,
   so the mouth floats with the face. Positions are in the characters' own 240×260 drawings. */
(() => {
  "use strict";
  // where the mouth sits in each drawing: left %, top %, width % of the picture
  const SPOT = { luna: [50, 59.5, 15], bigotes: [50, 51.8, 10], xochi: [50, 55.5, 12] };
  const COPY = ["animationName", "animationDuration", "animationDelay", "animationIterationCount", "animationTimingFunction", "maxWidth"];

  function wrap(img) {
    if (img.parentElement && img.parentElement.classList.contains("face")) return;
    const who = ((img.getAttribute("src") || "").match(/characters\/(\w+)\.svg/) || [])[1];
    if (!SPOT[who] || !img.complete && !img.getAttribute("src")) return;
    const cs = getComputedStyle(img);
    const face = document.createElement("span");
    face.className = `face ${who}`;
    COPY.forEach((k) => { face.style[k] = cs[k]; });
    img.replaceWith(face);
    face.append(img);
    Object.assign(img.style, { animation: "none", maxWidth: "none" });
    const m = document.createElement("i");
    m.className = "mouth";
    m.setAttribute("aria-hidden", "true");
    const [x, y, w] = SPOT[who];
    Object.assign(m.style, { left: `${x}%`, top: `${y}%`, width: `${w}%` });
    face.append(m);
  }
  const scan = () => document.querySelectorAll(".seat > img, .st-cast figure > img").forEach(wrap);
  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
  scan();
})();
