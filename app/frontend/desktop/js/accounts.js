/*
 * "Аккаунты" tab. Picking a platform opens its (currently placeholder)
 * detail panel - the actual login/auto-upload flow lands here later, so
 * this only owns the platform picker and the show/hide between the two.
 */
document.addEventListener("DOMContentLoaded", () => {
  const detail = document.getElementById("accounts-detail");
  const title = document.getElementById("accounts-detail-title");
  const grid = document.querySelector("#section-accounts .platform-grid");
  if (!detail) return;

  const LABELS = { tiktok: "TikTok", youtube: "YouTube" };

  document.querySelectorAll("#section-accounts .platform-card").forEach((card) => {
    card.addEventListener("click", () => {
      title.textContent = LABELS[card.dataset.platform] || card.dataset.platform;
      detail.classList.remove("hidden");
      grid.classList.add("hidden");
    });
  });

  document.getElementById("btn-accounts-back").addEventListener("click", () => {
    detail.classList.add("hidden");
    grid.classList.remove("hidden");
  });
});
