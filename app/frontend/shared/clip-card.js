/*
 * Shared clip-card rendering + sort/filter helpers.
 * Used by both the desktop results screen and the mobile transfer page
 * (stage 8) so the two never carry separate implementations of the same UI.
 */

function formatTime(sec) {
  sec = Math.round(sec);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function scoreBarColor(score) {
  if (score === null || score === undefined) return "var(--muted)";
  if (score >= 66) return "var(--accent-2)";
  if (score >= 33) return "var(--accent)";
  return "var(--danger)";
}

// clip: ClipMeta-shaped object. jobId: string. urls: {download, thumbnail}
function renderClipCard(jobId, clip, urls) {
  const el = document.createElement("div");
  el.className = "clip-card";

  const scoreHtml =
    clip.potential_score === null || clip.potential_score === undefined
      ? ""
      : `<div class="clip-score" title="Относительная оценка динамичности момента, не гарантия успеха в рекомендациях">
           <div class="clip-score-bar"><div style="width:${clip.potential_score}%;background:${scoreBarColor(clip.potential_score)}"></div></div>
           <span>${Math.round(clip.potential_score)}</span>
         </div>`;

  const label = clip.variation_index === 0 ? "Оригинал" : `Вариант ${clip.variation_index}`;

  el.innerHTML = `
    <img class="clip-thumb" src="${urls.thumbnail}" loading="lazy" alt="${label}">
    <div class="clip-info">
      <div class="clip-label">${label}</div>
      <div class="clip-time">${formatTime(clip.source_start)} – ${formatTime(clip.source_end)}</div>
      ${scoreHtml}
      <a class="btn btn-small" href="${urls.download}" download><span class="btn-icon icon-mask" style="mask-image:url(/assets/icon-download.svg);-webkit-mask-image:url(/assets/icon-download.svg);width:13px;height:13px;margin-right:5px;vertical-align:-2px"></span>Скачать</a>
    </div>
  `;
  return el;
}

function sortClips(clips, mode) {
  const arr = [...clips];
  if (mode === "score_desc") arr.sort((a, b) => (b.potential_score ?? -1) - (a.potential_score ?? -1));
  else if (mode === "score_asc") arr.sort((a, b) => (a.potential_score ?? -1) - (b.potential_score ?? -1));
  else arr.sort((a, b) => a.source_start - b.source_start);
  return arr;
}

function filterClipsByScore(clips, minScore) {
  if (!minScore) return clips;
  return clips.filter((c) => (c.potential_score ?? 0) >= minScore);
}

function groupByOriginal(clips) {
  // clip_id convention: "clip_000", variations share the same numeric prefix.
  const groups = new Map();
  for (const clip of clips) {
    const key = clip.clip_id.replace(/_var\d+$/, "");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(clip);
  }
  return [...groups.values()];
}
