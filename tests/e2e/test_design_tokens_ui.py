"""One design system: every font size and corner radius in the stylesheet comes from a small scale, and keyboard focus
is always visible. (Before, the stylesheet used 11 font sizes and 10 radii, and showed no focus at all.)"""

from uihelpers import open_app

FONT_SIZES = {10, 11, 12, 13, 15, 20}  # badges · labels · lists and buttons · body · documents and titles · page titles
RADII = {0, 4, 6, 10, 999}  # tags · buttons and cards · panels and popovers · pills (plus 50% for circles)

# Every px font size and corner radius declared in app.css, with the rule that declares it.
DECLARED = """() => {
  const sheet = [...document.styleSheets].find((s) => (s.href || '').endsWith('/static/app.css'));
  const out = { font: [], radius: [], undefined: [] };
  const walk = (rules) => { for (const r of rules) {
    if (r.cssRules) walk(r.cssRules);
    if (!r.style) continue;
    const px = (v) => (v.match(/-?[\\d.]+px/g) || []).map(parseFloat);
    for (const v of px(r.style.fontSize || '')) out.font.push([r.selectorText, v]);
    for (const c of ['borderTopLeftRadius', 'borderTopRightRadius', 'borderBottomLeftRadius', 'borderBottomRightRadius'])
      for (const v of px(r.style[c] || '')) out.radius.push([r.selectorText, v]);
    // A token must exist and resolve to the scale: a misspelt one makes the browser drop the whole declaration.
    for (const [, prop, value] of r.style.cssText.matchAll(/(font-size|font|border-radius)\s*:\s*([^;]+)/g))
      for (const [, name] of value.matchAll(/var\((--[\w-]+)\)/g)) {
        const resolved = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        if (!resolved) { out.undefined.push([r.selectorText, name]); continue; }
        for (const v of px(resolved)) out[prop === 'border-radius' ? 'radius' : 'font'].push([r.selectorText, v]);
      }
  } };
  walk(sheet.cssRules);
  return out;
}"""


def test_font_sizes_and_radii_come_from_the_scale(page, server, session):
    open_app(page)
    declared = page.evaluate(DECLARED)
    off_font = sorted({(sel, v) for sel, v in declared["font"] if v not in FONT_SIZES})
    off_radius = sorted({(sel, v) for sel, v in declared["radius"] if v not in RADII})
    assert not declared["undefined"], f"tokens that don't exist: {sorted(set(map(tuple, declared['undefined'])))}"
    assert not off_font, f"font sizes off the scale: {off_font}"
    assert not off_radius, f"radii off the scale: {off_radius}"
    root = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--fs-body').trim()")
    assert root == "13px"


def test_keyboard_focus_is_always_visible(page, server, session):
    open_app(page)
    page.mouse.click(5, 450)  # somewhere neutral, then move with the keyboard only
    seen = []
    for _ in range(12):
        page.keyboard.press("Tab")
        seen.append(page.evaluate("""() => { const el = document.activeElement, cs = getComputedStyle(el);
          const accent = () => { const p = document.createElement('i'); p.style.color = 'var(--accent)';
            document.body.append(p); const c = getComputedStyle(p).color; p.remove(); return c; };
          const ring = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 2;
          // Text fields show focus their own way: an accent border (on the composer, around the whole box).
          const box = el.closest('.composer-box') || el;
          const field = el.matches('input, textarea, select') && getComputedStyle(box).borderColor === accent();
          return { what: el.id || el.className || el.tagName, shown: ring || field }; }"""))
    hidden = [s["what"] for s in seen if not s["shown"]]
    assert not hidden, f"no visible focus on: {hidden}"


# Is focus visible on this element: a ring in a colour other than its own fill, or a field's accent border?
VISIBLE = """(el) => { const cs = getComputedStyle(el);
  const probe = document.createElement('i'); probe.style.color = 'var(--accent)'; document.body.append(probe);
  const accent = getComputedStyle(probe).color; probe.remove();
  const ring = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 2 && cs.outlineColor !== cs.backgroundColor;
  const edge = cs.borderTopColor === accent || cs.borderBottomColor === accent;
  return ring || edge; }"""


def test_the_focus_ring_shows_on_solid_accent_buttons(page, server, session):
    open_app(page)
    page.keyboard.press("Tab")  # keyboard mode: a focus() now shows the ring as it would from Tab
    send = page.locator("#sendBtn")
    send.evaluate("(el) => el.focus()")
    assert send.evaluate(VISIBLE), "Send: the ring is the same colour as the button"


def test_focus_shows_in_the_file_palette_and_the_code_editor(page, server, session):
    open_app(page)
    page.keyboard.press("Meta+p" if page.evaluate("navigator.platform").startswith("Mac") else "Control+p")
    box = page.locator("#paletteInput")
    box.wait_for()
    assert box.evaluate(VISIBLE), "the palette's search box shows no focus"
    page.keyboard.press("Escape")
    page.locator("#tree [data-file]", has_text="Makefile").click()
    page.locator(".ed-bar button", has_text="Edit").click()
    editor = page.locator(".code-edit")
    editor.wait_for()
    editor.focus()
    assert editor.evaluate(VISIBLE), "the code editor shows no focus"


# WCAG contrast, computed from the stylesheet as the page resolves it, in one theme. Text tokens against each surface;
# the text of every solid accent fill (any rule with color: var(--accent-fg), and its :hover) against that fill.
CONTRAST = """(theme) => {
  document.documentElement.dataset.theme = theme;
  const rgb = (value, prop = 'color') => { const p = document.createElement('i'); p.style[prop] = value; document.body.append(p);
    const c = getComputedStyle(p)[prop]; p.remove(); return c.match(/[\\d.]+/g).slice(0, 3).map(Number); };
  const lum = ([r, g, b]) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const low = [];
  const check = (fg, bg, min, fgVal = `var(${fg})`, bgVal = `var(${bg})`) => {
    const r = ratio(rgb(fgVal), rgb(bgVal, 'backgroundColor'));
    if (r < min) low.push(`${fg} on ${bg}: ${r.toFixed(2)} < ${min}`);
  };
  const surfaces = ['--bg-0', '--bg-1', '--bg-2', '--bg-3', '--bg-4'];
  for (const t of ['--muted', '--ok', '--warn', '--err', '--info', '--accent']) for (const s of surfaces) check(t, s, 4.5);
  for (const s of surfaces.slice(0, 4)) check('--faint', s, 3);
  const sheet = [...document.styleSheets].find((s) => (s.href || '').endsWith('/static/app.css'));
  const fills = new Map();  // selector -> its background, for rules that put --accent-fg text on a fill
  const rules = []; const walk = (rs) => { for (const r of rs) { if (r.cssRules) walk(r.cssRules); if (r.style) rules.push(r); } };
  walk(sheet.cssRules);
  const bgOf = (r) => r.style.backgroundColor || r.style.background;  // (a var() in the shorthand leaves the longhand empty)
  for (const r of rules) if (/var\\(--accent-fg\\)/.test(r.style.color) && bgOf(r)) fills.set(r.selectorText, bgOf(r));
  for (const r of rules) { const base = (r.selectorText || '').replace(/:hover$/, '');
    if (base !== r.selectorText && fills.has(base) && bgOf(r)) fills.set(r.selectorText, bgOf(r)); }
  for (const [sel, bg] of fills) check(`--accent-fg (${sel})`, bg, 4.5, 'var(--accent-fg)', bg);
  delete document.documentElement.dataset.theme;
  return { low, fills: [...fills.keys()] };
}"""


def test_text_tokens_meet_contrast_in_both_themes(page, server, session):
    open_app(page)
    for theme in ("dark", "light"):
        found = page.evaluate(CONTRAST, theme)
        assert {".btn.primary", ".btn.primary:hover", ".send", ".send:hover"} <= set(found["fills"]), found["fills"]
        assert not found["low"], f"{theme}: " + "; ".join(found["low"])


def test_the_two_light_theme_blocks_stay_identical(page, server, session):
    open_app(page)
    blocks = page.evaluate("""() => { const sheet = [...document.styleSheets].find((s) => (s.href || '').endsWith('/static/app.css'));
      const out = {}; const walk = (rs) => { for (const r of rs) { if (r.cssRules) walk(r.cssRules);
        if (r.selectorText === ':root:not([data-theme="dark"])' || r.selectorText === ':root[data-theme="light"]') out[r.selectorText] = r.style.cssText; } };
      walk(sheet.cssRules); return out; }""")
    assert len(blocks) == 2 and len(set(blocks.values())) == 1, blocks
