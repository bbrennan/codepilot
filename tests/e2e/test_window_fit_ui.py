"""The layout fits the window it's in. Pane sizes are remembered per browser, so sizes chosen on a big external monitor
come back on a laptop screen; they must shrink to fit there, and return when the window is big again."""

from uihelpers import open_app

BIG = {"width": 2560, "height": 1440}
LAPTOP = {"width": 1280, "height": 720}

# Sizes dragged out on a big monitor: each at the most its resizer allows.
SAVED_ON_BIG_MONITOR = """() => {
  localStorage.setItem('cp--sidebar-w', '560px');
  localStorage.setItem('cp--chat-w', '820px');
  localStorage.setItem('cp--panel-h', '640px');
}"""

GEOMETRY = """() => {
  const box = (sel) => { const r = document.querySelector(sel).getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height }; };
  return { w: innerWidth, h: innerHeight, side: box('.sidebar'), center: box('.center'), chat: box('.chat'),
           editor: box('#editor'), composer: box('#composerBox'), status: box('.statusbar') };
}"""


def geometry(page):
    return page.evaluate(GEOMETRY)


def assert_fits(g):
    assert g["chat"]["right"] <= g["w"] + 0.5, f"the chat runs off the right edge: {g['chat']} in {g['w']}px"
    assert g["composer"]["right"] <= g["w"] + 0.5 and g["composer"]["bottom"] <= g["status"]["top"] + 0.5, \
        f"the message box isn't fully on screen: {g['composer']}"
    assert g["center"]["width"] >= 279.5, f"the editor is squeezed to {g['center']['width']}px wide"
    assert g["editor"]["height"] >= 119.5, f"the bottom panel leaves the editor {g['editor']['height']}px tall"


def test_sizes_saved_on_a_big_monitor_fit_a_laptop_window(page, server, session):
    page.set_viewport_size(LAPTOP)
    page.add_init_script(f"({SAVED_ON_BIG_MONITOR})()")
    open_app(page)
    assert_fits(geometry(page))


def test_unplugging_the_monitor_shrinks_the_panes_and_plugging_it_back_restores_them(page, server, session):
    page.set_viewport_size(BIG)
    page.add_init_script(f"({SAVED_ON_BIG_MONITOR})()")
    open_app(page)
    before = geometry(page)
    assert round(before["chat"]["width"]) == 820 and round(before["side"]["width"]) == 560

    page.set_viewport_size(LAPTOP)  # what the window does when the external display goes away
    page.wait_for_function("() => document.querySelector('.chat').getBoundingClientRect().right <= innerWidth")
    assert_fits(geometry(page))

    page.set_viewport_size(BIG)
    page.wait_for_function("() => Math.round(document.querySelector('.chat').getBoundingClientRect().width) === 820")
    after = geometry(page)
    assert round(after["side"]["width"]) == 560 and round(after["editor"]["height"]) == round(before["editor"]["height"])
    assert page.evaluate("localStorage.getItem('cp--chat-w')") == "820px"  # fitting never overwrote the choice


def test_dragging_the_chat_wider_stops_at_the_window_edge(page, server, session):
    page.set_viewport_size({"width": 1280, "height": 800})
    open_app(page)
    handle = page.locator("#chatResizer").bounding_box()
    page.mouse.move(handle["x"] + 2, handle["y"] + 200)
    page.mouse.down()
    page.mouse.move(60, handle["y"] + 200, steps=8)
    page.mouse.up()
    assert_fits(geometry(page))


def test_hiding_the_sidebar_gives_the_chat_its_chosen_width_back(page, server, session):
    page.set_viewport_size(LAPTOP)
    page.add_init_script(f"({SAVED_ON_BIG_MONITOR})()")
    open_app(page)
    assert geometry(page)["chat"]["width"] < 820
    page.click("#toggleSidebar")
    page.wait_for_function("() => Math.round(document.querySelector('.chat').getBoundingClientRect().width) === 820")
    assert_fits(geometry(page))
