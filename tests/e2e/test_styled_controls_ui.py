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


def test_small_dropdowns_leave_room_for_their_chevron(page, server, session):
    open_app(page)
    for sel in ("#modeSelect", "#tier"):
        pad = page.locator(sel).evaluate("(el) => parseFloat(getComputedStyle(el).paddingRight)")
        assert pad >= 20, f"{sel}: {pad}px leaves the label running under the chevron"


def test_the_open_folder_switch_is_a_switch_too(page, server, session):
    open_app(page)
    page.click("#openFolderBtn")
    hidden = page.locator("#fdHidden")
    hidden.wait_for()
    look = hidden.evaluate(LOOK)
    pad = hidden.evaluate("(el) => getComputedStyle(el).paddingLeft")
    assert look["appearance"] == "none" and round(look["width"]) == 26 and round(look["height"]) == 14, look
    assert pad == "0px"


def test_keyboard_focus_shows_on_a_switch_that_is_on(page, server, session):
    open_app(page)
    switch = page.locator("#autoApprove")
    page.locator("label.toggle", has=switch).click()
    page.wait_for_function(f"() => getComputedStyle(document.querySelector('#autoApprove')).backgroundColor === ({ACCENT})()")
    page.keyboard.press("Tab")
    switch.evaluate("(el) => el.focus()")
    ring = switch.evaluate("""(el) => { const cs = getComputedStyle(el);
      return { style: cs.outlineStyle, offset: parseFloat(cs.outlineOffset), color: cs.outlineColor, bg: cs.backgroundColor }; }""")
    assert ring["style"] != "none" and (ring["offset"] >= 0 or ring["color"] != ring["bg"]), ring


def test_switches_dont_animate_when_the_system_asks_for_less_motion(page, server, session):
    page.emulate_media(reduced_motion="reduce")
    open_app(page)
    durations = page.locator("#autoApprove").evaluate("""(el) => [getComputedStyle(el).transitionDuration,
      getComputedStyle(el, '::before').transitionDuration]""")
    assert all(set(d.replace("s", "").split(", ")) <= {"0"} for d in durations), durations  # the knob too
