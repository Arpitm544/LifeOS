export const sidebarStorageKey = "lifeos.sidebar";

// Runs before the page paints so a collapsed sidebar does not flash open on load.
export const sidebarInitScript = `(function(){try{if(localStorage.getItem(${JSON.stringify(sidebarStorageKey)})==="collapsed")document.documentElement.dataset.sidebar="collapsed"}catch{}})()`;

export const isSidebarCollapsed = () => document.documentElement.dataset.sidebar === "collapsed";

export function setSidebarCollapsed(collapsed: boolean) {
  if (collapsed) document.documentElement.dataset.sidebar = "collapsed";
  else delete document.documentElement.dataset.sidebar;
  try { localStorage.setItem(sidebarStorageKey, collapsed ? "collapsed" : "expanded"); } catch { /* Still works for this visit without storage. */ }
}
