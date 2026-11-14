import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";
import { getTheme, resolveTheme, setTheme, subscribeTheme, themeInitScript, themeStorageKey } from "../src/lib/theme.ts";

test("theme resolution and early script prefer saved choices and handle unavailable storage", () => {
  for (const systemDark of [true, false]) {
    assert.equal(resolveTheme("light", systemDark), "light");
    assert.equal(resolveTheme("dark", systemDark), "dark");
    for (const saved of [null, "invalid", ""]) assert.equal(resolveTheme(saved, systemDark), systemDark ? "dark" : "light");
    for (const saved of [null, "light", "dark", "invalid"]) {
      const document = { documentElement: { dataset: { theme: "" } } };
      vm.runInNewContext(themeInitScript, { document, localStorage: { getItem: () => saved }, window: { matchMedia: () => ({ matches: systemDark }) } });
      assert.equal(document.documentElement.dataset.theme, resolveTheme(saved, systemDark));
    }
    const document = { documentElement: { dataset: { theme: "" } } };
    vm.runInNewContext(themeInitScript, { document, localStorage: { getItem: () => { throw new Error("blocked"); } }, window: { matchMedia: () => ({ matches: systemDark }) } });
    assert.equal(document.documentElement.dataset.theme, systemDark ? "dark" : "light");
  }
});

test("theme changes persist, sync across controls and tabs, and fall back to session when storage is blocked", () => {
  const originals = ["window", "document", "localStorage"].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)] as const);
  const saved = new Map<string, string>();
  const media = Object.assign(new EventTarget(), { matches: true });
  const host = Object.assign(new EventTarget(), { matchMedia: () => media });
  let blocked = false;
  const storage = {
    getItem: (key: string) => { if (blocked) throw new Error("blocked"); return saved.get(key) ?? null; },
    setItem: (key: string, value: string) => { if (blocked) throw new Error("blocked"); saved.set(key, value); },
  };
  Object.defineProperty(globalThis, "window", { configurable: true, value: host });
  Object.defineProperty(globalThis, "document", { configurable: true, value: { documentElement: { dataset: { theme: "light" } } } });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: storage });
  let dispose = () => {};
  try {
    let changes = 0;
    dispose = subscribeTheme(() => changes++);
    setTheme("dark");
    assert.equal(getTheme(), "dark");
    assert.equal(saved.get(themeStorageKey), "dark");
    assert.equal(changes, 1);
    setTheme("light");
    media.dispatchEvent(new Event("change"));
    assert.equal(getTheme(), "light", "manual choice survives system changes");
    saved.set(themeStorageKey, "dark");
    host.dispatchEvent(Object.assign(new Event("storage"), { key: themeStorageKey, newValue: "dark" }));
    assert.equal(getTheme(), "dark", "other tabs update this control");
    saved.delete(themeStorageKey);
    host.dispatchEvent(Object.assign(new Event("storage"), { key: themeStorageKey, newValue: null }));
    media.matches = false;
    media.dispatchEvent(new Event("change"));
    assert.equal(getTheme(), "light", "clearing a preference resumes system theme");
    blocked = true;
    assert.doesNotThrow(() => setTheme("dark"));
    media.dispatchEvent(new Event("change"));
    assert.equal(getTheme(), "dark", "session choice works when storage is blocked");
    dispose();
    const last = changes;
    setTheme("light");
    assert.equal(changes, last, "unmount removes listeners");
  } finally {
    dispose();
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
  }
});
