/*
 * Mobile transfer page: lists every finished job's clips with download
 * links. Reuses the same renderClipCard/groupByOriginal helpers as the
 * desktop results screen (js/shared/clip-card.js) so both stay visually
 * consistent without duplicating that logic.
 */
async function loadJobs() {
  const content = document.getElementById("content");
  let jobs;
  try {
    const res = await fetch("/api/jobs");
    jobs = await res.json();
  } catch {
    content.innerHTML = `<p class="empty">Не удалось связаться с компьютером. Убедитесь, что телефон в той же Wi-Fi сети.</p>`;
    return;
  }

  const done = jobs.filter((j) => j.status === "done");
  if (done.length === 0) {
    content.innerHTML = `<p class="empty">Пока нет готовых клипов. Запустите обработку на компьютере и обновите эту страницу.</p>`;
    return;
  }

  content.innerHTML = "";
  for (const job of done) {
    const section = document.createElement("section");
    section.className = "job-section";

    const header = document.createElement("div");
    header.className = "job-header";
    header.innerHTML = `
      <h2>${job.title}</h2>
      <a class="download-all" href="/api/jobs/${job.job_id}/download-all">Скачать всё (zip)</a>
    `;
    section.appendChild(header);

    const grid = document.createElement("div");
    grid.className = "clip-grid";
    section.appendChild(grid);
    content.appendChild(section);

    try {
      const res = await fetch(`/api/jobs/${job.job_id}/clips`);
      const manifest = await res.json();
      const groups = groupByOriginal(manifest.clips);
      for (const group of groups) {
        for (const clip of group) {
          const card = renderClipCard(job.job_id, clip, {
            download: `/api/jobs/${job.job_id}/download/${clip.clip_id}`,
            thumbnail: `/api/jobs/${job.job_id}/thumbnail/${clip.clip_id}`,
          });
          grid.appendChild(card);
        }
      }
    } catch {
      grid.innerHTML = `<p class="empty">Не удалось загрузить клипы для этого видео.</p>`;
    }
  }
}

loadJobs();
