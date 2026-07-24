/*
 * Desktop notification toggle popup, opened from the sidebar footer next to
 * "Тема". The OS notification itself only ever fires from the backend on
 * job done/error - this popup just reads and writes the on/off preference
 * it checks before doing so.
 */
document.addEventListener("DOMContentLoaded", () => {
  const overlay = document.getElementById("notif-overlay");
  const toggle = document.getElementById("notif-toggle");

  document.getElementById("btn-notifications").addEventListener("click", async () => {
    overlay.classList.remove("hidden");
    try {
      const res = await fetch("/api/settings/notifications");
      const data = await res.json();
      toggle.checked = data.enabled;
    } catch {
      // keep whatever the checkbox last showed - a transient fetch hiccup
      // shouldn't block opening the popup
    }
  });

  document.getElementById("btn-notif-close").addEventListener("click", () => overlay.classList.add("hidden"));
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.classList.add("hidden");
  });

  toggle.addEventListener("change", () => {
    fetch("/api/settings/notifications", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: toggle.checked }),
    }).catch(() => {});
  });
});
