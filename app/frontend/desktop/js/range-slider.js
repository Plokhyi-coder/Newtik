/*
 * Dual-handle drag slider for picking the trim range (screen 1). Defaults to
 * the full video (0..duration) so there is always a valid selection. Each
 * thumb has an editable timecode label above it - click it to type an exact
 * value instead of dragging.
 */
const RangeSlider = (() => {
  const MIN_GAP_SEC = 1;

  let duration = 0;
  let startSec = 0;
  let endSec = 0;
  let dragging = null; // "start" | "end" | null
  let wired = false;

  let track, fill, wrapStart, wrapEnd, thumbStart, thumbEnd, labelStart, labelEnd;

  function cacheEls() {
    track = document.getElementById("range-track");
    fill = document.getElementById("range-fill");
    wrapStart = document.getElementById("thumb-wrap-start");
    wrapEnd = document.getElementById("thumb-wrap-end");
    thumbStart = document.getElementById("range-thumb-start");
    thumbEnd = document.getElementById("range-thumb-end");
    labelStart = document.getElementById("range-label-start");
    labelEnd = document.getElementById("range-label-end");
  }

  function secToClock(sec) {
    sec = Math.max(0, Math.round(sec));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return [h, m, s].map((v) => String(v).padStart(2, "0")).join(":");
  }

  function clockToSec(value) {
    if (!value || !value.trim()) return null;
    const parts = value.trim().split(":").map(Number);
    if (parts.some((p) => Number.isNaN(p))) return null;
    let sec = 0;
    for (const p of parts) sec = sec * 60 + p;
    return sec;
  }

  function pct(sec) {
    if (!duration) return 0;
    return Math.min(100, Math.max(0, (sec / duration) * 100));
  }

  function render() {
    const startPct = pct(startSec);
    const endPct = pct(endSec);
    wrapStart.style.left = `${startPct}%`;
    wrapEnd.style.left = `${endPct}%`;
    fill.style.left = `${startPct}%`;
    fill.style.width = `${Math.max(0, endPct - startPct)}%`;
    if (document.activeElement !== labelStart) labelStart.value = secToClock(startSec);
    if (document.activeElement !== labelEnd) labelEnd.value = secToClock(endSec);
  }

  function secFromClientX(clientX) {
    const rect = track.getBoundingClientRect();
    const x = Math.min(rect.width, Math.max(0, clientX - rect.left));
    const frac = rect.width ? x / rect.width : 0;
    return Math.round(frac * duration);
  }

  function onPointerDown(which) {
    return (e) => {
      e.preventDefault();
      dragging = which;
      (which === "start" ? thumbStart : thumbEnd).classList.add("dragging");
    };
  }

  function onPointerMove(e) {
    if (!dragging) return;
    const sec = secFromClientX(e.clientX);
    if (dragging === "start") {
      startSec = Math.max(0, Math.min(sec, endSec - MIN_GAP_SEC));
    } else {
      endSec = Math.min(duration, Math.max(sec, startSec + MIN_GAP_SEC));
    }
    render();
  }

  function onPointerUp() {
    if (!dragging) return;
    dragging = null;
    thumbStart.classList.remove("dragging");
    thumbEnd.classList.remove("dragging");
  }

  function commitLabel(which, input) {
    const sec = clockToSec(input.value);
    if (sec === null) {
      render(); // invalid text - just revert to the last valid value
      return;
    }
    const clamped = Math.min(duration, Math.max(0, sec));
    if (which === "start") {
      startSec = Math.max(0, Math.min(clamped, endSec - MIN_GAP_SEC));
    } else {
      endSec = Math.min(duration, Math.max(clamped, startSec + MIN_GAP_SEC));
    }
    render();
  }

  function wireEvents() {
    if (wired) return;
    wired = true;

    thumbStart.addEventListener("mousedown", onPointerDown("start"));
    thumbEnd.addEventListener("mousedown", onPointerDown("end"));
    window.addEventListener("mousemove", onPointerMove);
    window.addEventListener("mouseup", onPointerUp);

    for (const [input, which] of [[labelStart, "start"], [labelEnd, "end"]]) {
      input.addEventListener("focus", () => input.select());
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") input.blur();
      });
      input.addEventListener("blur", () => commitLabel(which, input));
    }
  }

  function init(durationSec) {
    cacheEls();
    duration = Math.max(1, Math.round(durationSec || 0));
    startSec = 0;
    endSec = duration;
    render();
    wireEvents();
  }

  function getRange() {
    return { start: startSec, end: endSec, duration };
  }

  return { init, getRange };
})();
