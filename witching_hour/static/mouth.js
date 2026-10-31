/* Moving mouths: while a character talks (.speaking in the séance, .talking on the first screen),
   an open mouth flaps over their drawn smile. Each picture is wrapped in a .face that carries its float,
   so the mouth floats with the face. Positions are in the characters' own 240×260 drawings. */
(() => {
  "use strict";
  // the drawn smile in each 240×260 drawing: centre x, centre y, width, height, and the skin around it,
  // so a patch of skin hides the smile while the open mouth talks
  const SPOT = { luna: [120, 156, 40, 18, "#fbf7ff"], bigotes: [120, 136, 26, 11, "#574c7a"], xochi: [120, 145, 34, 21, "#6e7a97"] };
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
    const [x, y, w, h, skin] = SPOT[who];
    Object.assign(m.style, { left: `${x / 240 * 100}%`, top: `${y / 260 * 100}%`, width: `${w / 240 * 100}%`, height: `${h / 260 * 100}%`, background: skin });
    face.append(m);
  }
  const scan = () => document.querySelectorAll(".seat > img, .st-cast figure > img").forEach(wrap);
  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
  scan();
})();
