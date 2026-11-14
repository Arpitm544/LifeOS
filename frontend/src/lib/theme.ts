export type Theme = "light" | "dark";
export const themeStorageKey = "lifeos.theme";

export function resolveTheme(saved: string | null, systemDark: boolean): Theme {
  return saved === "light" || saved === "dark" ? saved : systemDark ? "dark" : "light";
}

// Runs before the page paints so a saved dark theme does not flash light.
export const themeInitScript = `(function(){var saved=null;try{saved=localStorage.getItem("lifeos.theme")}catch{}document.documentElement.dataset.theme=saved==="light"||saved==="dark"?saved:window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"})()`;

let sessionTheme: Theme | null = null;
const themeEvent = "lifeos-theme-change";
export const getTheme = () => document.documentElement.dataset.theme === "dark" ? "dark" : "light";

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new Event(themeEvent));
}

export function subscribeTheme(callback: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const systemChange = () => {
    let saved: string | null = sessionTheme;
    try { saved = localStorage.getItem(themeStorageKey) ?? sessionTheme; } catch { /* Keep the session choice when storage is unavailable. */ }
    apply(resolveTheme(saved, media.matches));
  };
  const storageChange = (event: StorageEvent) => {
    if (event.key !== themeStorageKey && event.key !== null) return;
    sessionTheme = null;
    apply(resolveTheme(event.newValue, media.matches));
  };
  window.addEventListener(themeEvent, callback);
  window.addEventListener("storage", storageChange);
  media.addEventListener("change", systemChange);
  return () => {
    window.removeEventListener(themeEvent, callback);
    window.removeEventListener("storage", storageChange);
    media.removeEventListener("change", systemChange);
  };
}

export function setTheme(theme: Theme) {
  sessionTheme = theme;
  try { localStorage.setItem(themeStorageKey, theme); } catch { /* The theme still works for this session. */ }
  apply(theme);
}
