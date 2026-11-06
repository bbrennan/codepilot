"""Controls look like the app, not like the browser: dropdowns get its border, radius and chevron, and on/off settings
are switches. Underneath they stay native (a <select>, a checkbox), so keyboards, screen readers and option groups
work as before."""

from uihelpers import open_app

LOOK = """(el) => { const cs = getComputedStyle(el);
  return { tag: el.tagName, appearance: cs.appearance || cs.webkitAppearance, image: cs.backgroundImage,
           radius: cs.borderTopLeftRadius, width: el.getBoundingClientRect().width,
           height: el.getBoundingClientRect().height, bg: cs.backgroundColor, role: el.getAttribute('role') }; }"""
ACCENT = """() => { const p = document.createElement('i'); p.style.color = 'var(--accent)'; document.body.append(p);
  const c = getComputedStyle(p).color; p.remove(); return c; }"""


def test_dropdowns_have_the_apps_look_and_still_work_natively(page, server, session):
    open_app(page)
    page.wait_for_function("() => document.querySelector('#tier option[value=\"tier:main\"]')")
    for sel in ("#modeSelect", "#tier"):
        look = page.locator(sel).evaluate(LOOK)
        assert look["tag"] == "SELECT" and look["appearance"] == "none", (sel, look)
        assert "gradient" in look["image"] and look["radius"] == "6px", (sel, look)  # its own chevron, the shared radius
    page.select_option("#modeSelect", "plan")
    assert page.locator("#modeSelect").input_value() == "plan"


def test_settings_are_switches_that_click_and_keyboard_both_toggle(page, server, session):
    open_app(page)
    switch = page.locator("#autoApprove")
    look = switch.evaluate(LOOK)
    assert look["role"] == "switch" and look["appearance"] == "none", look
    assert look["width"] > look["height"] * 1.5, look  # a pill, not a box
    page.locator("label.toggle", has=switch).click()
    assert switch.is_checked()
    # On: filled with the accent (after its short colour transition).
    page.wait_for_function(f"() => getComputedStyle(document.querySelector('#autoApprove')).backgroundColor === ({ACCENT})()")
    switch.focus()
    page.keyboard.press("Space")
    assert not switch.is_checked()
