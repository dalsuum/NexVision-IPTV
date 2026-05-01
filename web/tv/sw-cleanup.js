(async () => {
  const path = window.location.pathname;
  // Only intercept VOD admin + dashboard paths — not the TV client root
  if (!path.startsWith('/vod/admin') && path !== '/vod' && path !== '/vod/') return;

  // Loop guard: max 2 attempts to kill the SW, then give up and let the
  // self-destruct sw.js handle it via the browser's background update mechanism.
  const SS_KEY = 'nv_sw_kill';
  const n = parseInt(sessionStorage.getItem(SS_KEY) || '0', 10);
  if (n >= 2) { sessionStorage.removeItem(SS_KEY); return; }
  sessionStorage.setItem(SS_KEY, String(n + 1));

  // Hide the TV shell while we do the cleanup
  document.documentElement.style.display = 'none';

  // Unregister every service worker on this origin
  try {
    const regs = await navigator.serviceWorker.getRegistrations();
    await Promise.all(regs.map(r => r.unregister()));
  } catch (e) {}

  // Nuke every cache entry
  try {
    const keys = await caches.keys();
    await Promise.all(keys.map(k => caches.delete(k)));
  } catch (e) {}

  // Navigate to the original clean path — no accumulated query params
  window.location.replace(path);
})();
