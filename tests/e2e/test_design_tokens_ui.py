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
