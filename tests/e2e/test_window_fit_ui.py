"""The layout fits the window it's in. Pane sizes are remembered per browser, so sizes chosen on a big external monitor
come back on a laptop screen; they must shrink to fit there, and return when the window is big again."""

import pytest

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


def test_hiding_the_sidebar_gives_the_chat_back_what_the_editor_can_spare(page, server, session):
    page.set_viewport_size(LAPTOP)
    page.add_init_script(f"({SAVED_ON_BIG_MONITOR})()")
    open_app(page)
    before = geometry(page)["chat"]["width"]
    page.click("#toggleSidebar")
    # The chosen 820px would leave the editor 408px; it gets all but the editor's 440: 1280 - 48 - 4 - 440 = 788.
    page.wait_for_function("() => Math.round(document.querySelector('.chat').getBoundingClientRect().width) === 788")
    assert before < 788
    assert_fits(geometry(page))


# Every button in the title bar: on screen, its full size, and the thing under its centre.
TITLE_BAR = """() => [...document.querySelectorAll('.titlebar > button')].map((b) => {
  const r = b.getBoundingClientRect(), hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return { id: b.id, onScreen: r.left >= 0 && r.right <= innerWidth + 0.5, full: r.width >= 26 && r.height >= 26,
           hit: !!hit && b.contains(hit), title: b.title };
})"""

BRAND_WORD_AT = 560  # app.css: under this the title bar shows the logo without its word; the folder's name keeps room


@pytest.mark.parametrize("width", [600, BRAND_WORD_AT + 1, BRAND_WORD_AT - 1, 480])
def test_the_title_bar_fits_a_small_window_and_the_page_never_scrolls_sideways(page, server, width):
    folder = server.repo.parent / "a-folder-with-a-rather-long-name"  # long enough that its name has to shrink
    folder.mkdir()
    (folder / "notes.txt").write_text("hi\n")
    server.store.create_session(str(folder), "main")
    page.set_viewport_size({"width": width, "height": 800})
    open_app(page)
    scroll = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert scroll[0] <= scroll[1], f"the page scrolls sideways: {scroll[0]}px of content in {scroll[1]}px"
    buttons = page.evaluate(TITLE_BAR)
    off = [b for b in buttons if not (b["onScreen"] and b["full"] and b["hit"] and b["title"])]
    assert not off, f"title bar buttons cut off, squashed or covered at {width}px: {off}"
    name = page.evaluate("(() => { const n = document.querySelector('#workspaceName');"
                         " return [n.textContent, n.scrollWidth > n.clientWidth]; })()")
    assert name[0] == folder.name and name[1], f"the folder's name isn't long enough to test: {name}"
    assert page.locator("#workspaceBtn").bounding_box()["width"] >= 100
    word = page.evaluate("document.querySelector('.brand-name')?.getBoundingClientRect().width ?? 0")
    assert (word > 0) == (width > BRAND_WORD_AT)


# layout.js: the editor keeps 440px while the sidebar and chat can shrink; under 400px even with both at their
# minimums (180 + 300), the sidebar steps aside. 48 (activity bar) + 8 (resizers) + 180 + 300 + 400 = 936.
COMFORT, FLOOR_WINDOW = 440, 936

SIDEBAR_STATE = """() => { const ide = document.getElementById('ide'), s = document.querySelector('.sidebar');
  return { auto: ide.classList.contains('auto-no-sidebar'), shown: s.getBoundingClientRect().width > 0,
           saved: localStorage.getItem('cp-no-sidebar'), side: s.getBoundingClientRect().width,
           chat: document.querySelector('.chat').getBoundingClientRect().width,
           editor: document.querySelector('.center').getBoundingClientRect().width }; }"""

# Watches #ide for a second: any class or size change after the layout has settled is the layout fighting itself.
SETTLED = """() => new Promise((done) => {
  const ide = document.getElementById('ide');
  const chat = () => document.querySelector('.chat').getBoundingClientRect().width;
  let changes = 0; const before = chat();
  const watch = new MutationObserver((records) => { changes += records.length; });
  watch.observe(ide, { attributes: true, attributeFilter: ['class', 'style'] });
  setTimeout(() => { watch.disconnect(); done({ changes, before, after: chat(), cls: ide.className }); }, 1000);
})"""


def sidebar(page):
    return page.evaluate(SIDEBAR_STATE)


def test_at_a_laptop_size_the_sidebar_and_chat_shrink_before_the_editor_goes_under_440(page, server, session):
    page.set_viewport_size({"width": 1024, "height": 700})
    open_app(page)
    g = geometry(page)
    assert g["center"]["width"] >= COMFORT - 0.5, f"the editor is {g['center']['width']}px"
    assert g["side"]["width"] >= 180 and g["chat"]["width"] >= 300
    assert_fits(g)


def test_a_wide_saved_chat_still_leaves_the_editor_440_and_stays_saved(page, server, session):
    page.set_viewport_size({"width": 1024, "height": 700})
    page.add_init_script("localStorage.setItem('cp--chat-w', '820px')")
    open_app(page)
    assert geometry(page)["center"]["width"] >= COMFORT - 0.5
    assert page.evaluate("localStorage.getItem('cp--chat-w')") == "820px"


@pytest.mark.parametrize("width", [FLOOR_WINDOW, FLOOR_WINDOW - 1, 821, 820])
def test_the_sidebar_steps_aside_only_where_the_editor_cannot_get_400(page, server, session, width):
    page.set_viewport_size({"width": width, "height": 700})
    open_app(page, wait_tree=False)
    s = sidebar(page)
    stepped_aside = 821 <= width < FLOOR_WINDOW  # 820 and under is the stacked layout
    assert s["auto"] == stepped_aside and s["shown"] != stepped_aside, s
    assert s["saved"] != "1"
    if width > 820:
        assert s["editor"] >= 399.5, s


def test_at_900_the_sidebar_steps_aside_settles_and_comes_back_at_1440(page, server, session):
    page.set_viewport_size({"width": 900, "height": 700})
    page.add_init_script("localStorage.setItem('cp--sidebar-w', '300px'); localStorage.setItem('cp--chat-w', '500px')")
    open_app(page, wait_tree=False)
    page.wait_for_function("() => document.getElementById('ide').classList.contains('auto-no-sidebar')")
    settled = page.evaluate(SETTLED)
    assert settled["changes"] == 0 and settled["before"] == settled["after"], settled
    s = sidebar(page)
    assert not s["shown"] and s["saved"] != "1" and s["editor"] >= COMFORT - 0.5, s
    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_function("() => !document.getElementById('ide').classList.contains('auto-no-sidebar')")
    s = sidebar(page)
    assert round(s["side"]) == 300 and round(s["chat"]) == 500, s
    assert page.evaluate("[localStorage.getItem('cp--sidebar-w'), localStorage.getItem('cp--chat-w')]") == \
        ["300px", "500px"]


@pytest.mark.parametrize("how", ["button", "shortcut", "active view's icon", "another view's icon"])
def test_showing_the_sidebar_yourself_wins_until_the_window_is_resized(page, server, session, how):
    page.set_viewport_size({"width": 900, "height": 700})
    open_app(page, wait_tree=False)
    page.wait_for_function("() => document.getElementById('ide').classList.contains('auto-no-sidebar')")
    if how == "button":
        page.click("#toggleSidebar")
    elif how == "shortcut":
        page.keyboard.press("ControlOrMeta+b")
    elif how == "active view's icon":
        page.click("#activitybar button.on")
    else:
        page.click("#activitybar [data-view=search]")
    page.wait_for_function("() => document.querySelector('.sidebar').getBoundingClientRect().width > 0")
    page.wait_for_function("() => state.workspace")  # (openFile needs the session's folder, which may still be loading)
    page.evaluate("openFile('agent/core.py')")
    page.locator("#fEdit").wait_for()
    settled = page.evaluate(SETTLED)
    assert settled["changes"] == 0, settled
    s = sidebar(page)
    assert s["shown"] and not s["auto"] and s["saved"] != "1", s
    page.set_viewport_size({"width": 905, "height": 700})
    page.wait_for_function("() => document.getElementById('ide').classList.contains('auto-no-sidebar')")
    assert not sidebar(page)["shown"]


def test_hiding_the_sidebar_yourself_is_saved_and_kept_when_the_window_grows(page, server, session):
    page.set_viewport_size({"width": 1440, "height": 900})
    open_app(page, wait_tree=False)
    page.click("#toggleSidebar")
    page.set_viewport_size({"width": 900, "height": 700})
    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_timeout(200)
    s = sidebar(page)
    assert not s["shown"] and s["saved"] == "1", s
