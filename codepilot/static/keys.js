"use strict";
// Shortcuts written one way per platform, wherever they're shown: on macOS as its menus write them (⌘P, ⌥W, ⌃`, ⌘⌫:
// symbols, no plus); elsewhere as words joined by "+" (Ctrl+P, Alt+W, Ctrl+`, Ctrl+Backspace). A shortcut is described
// the way the key handlers read it: "mod" is ⌘ on a Mac and Ctrl elsewhere; "ctrl" is the Control key everywhere.
// Loaded before app.js, which titles its buttons as it loads, so it uses none of app.js's helpers.

const KEYS_MAC = /Mac|iPhone|iPad/.test(navigator.platform);
const KEY_MODS = { mod: ["⌘", "Ctrl"], ctrl: ["⌃", "Ctrl"], alt: ["⌥", "Alt"], shift: ["⇧", "Shift"] };
const KEY_NAMES = { backspace: ["⌫", "Backspace"], delete: ["⌦", "Delete"], enter: ["Enter", "Enter"], escape: ["Esc", "Esc"] };

function keyLabel(combo) {
  const parts = String(combo).split("+");
  const key = parts.pop(), i = KEYS_MAC ? 0 : 1;
  const mods = parts.map((m) => KEY_MODS[m.toLowerCase()]?.[i] ?? m);
  const name = KEY_NAMES[key.toLowerCase()]?.[i] ?? (key.length === 1 ? key.toUpperCase() : key);
  return KEYS_MAC ? mods.join("") + name : [...mods, name].join("+");
}
