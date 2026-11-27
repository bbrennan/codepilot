"""Narrow panes keep every control. Below a set width a toolbar's buttons show icons, each with a tooltip,
instead of words; the path (or the terminal's folder) is what gets shortened. Widths are set by dragging the chat's
edge, as a user would, and the checks are geometry (a button inside its bar, and the thing under its centre), never
a text width: CI renders a different font.

The thresholds are measured (Chrome, with Verdana standing in for CI's wider font): a markdown toolbar with words needs
about 600px, every other editor toolbar under 500px; with icons, a markdown toolbar keeps its Preview/Source words down
to about 425px. The terminal's toolbar with words needs about 390px."""

import pytest

from uihelpers import open_app

MARKDOWN_AT, LABELS_AT, COMPACT_AT, TERMINAL_AT = 640, 520, 420, 420  # app.css: the editor's and panel's queries

# Each toolbar: how to open its tab, and the controls it must keep.
BARS = {
    "file": ("openFile('agent/core.py')", ["#fAdd", "#fAsk", "#fEdit", "#fCopy", "#fReload"]),
    "markdown": ("openFile('README.md')",
                 ["#fAdd", "#fAsk", "[data-view-mode=preview]", "[data-view-mode=source]", "#fEdit", "#fCopy",
                  "#fReload"]),
    "preview": ("openFile('README.md', undefined, 'preview')",
                ["[data-view-mode=preview]", "[data-view-mode=source]", "#fEdit", "#fAdd", "#fReload"]),
    "editing": ("openFile('README.md').then(() => editFile('file:README.md'))", ["#fEditPreview", "#fSave", "#fDone"]),
    "trace": ("openTrace('traces/journey_1.json')", ["#tAsk", "#tRef"]),
    "binary": ("openFile('logo.bin')", ["#fCopy"]),
    "spec": ("loadSpecs().then(() => openSpec('demo'))", ["[data-sp-view=requirements]", "[data-sp-view=design]",
                                                           "[data-sp-view=tasks]", "[data-sp-view=implement]"]),
}
TERMINAL = ["#termSelect", "#termSendSel", "#termNew", "#termRename", "#termKill", "#termMore"]

# For each control: inside its bar, the thing at its centre is itself, its tooltip, and whether its words show.
CHECK = """(sels) => {
  const first = document.querySelector(sels[0]);
  const bar = first.closest('.ed-bar, .term-bar'), b = bar.getBoundingClientRect();
  const out = sels.map((s) => {
    const el = bar.querySelector(s), r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    const lbl = el.querySelector('.lbl');
    return { s, inside: r.width > 0 && r.left >= b.left - 0.5 && r.right <= b.right + 0.5 && r.top >= b.top - 0.5
                        && r.bottom <= b.bottom + 0.5,
             hit: !!hit && el.contains(hit), title: el.title,
             words: lbl ? lbl.getBoundingClientRect().width > 2 : null };
  });
  return { controls: out, overflow: bar.scrollWidth - bar.clientWidth,
           count: [...bar.querySelectorAll(':scope > .muted')].some((m) => m.getBoundingClientRect().width > 0) };
}"""


def editor_width(page):
    return page.evaluate("document.querySelector('.editor').getBoundingClientRect().width")


def drag_editor_to(page, width):
    """Drag the chat's edge until the editor is `width` wide. A width you drag to may be under what fitting gives."""
    handle = page.locator("#chatResizer").bounding_box()
    x, y = handle["x"] + 2, handle["y"] + 200
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - (editor_width(page) - width), y, steps=4)
    page.mouse.up()
    assert abs(editor_width(page) - width) < 0.6, f"the editor is {editor_width(page)}px, not {width}px"


def setup(page, server):
    (server.repo / "README.md").write_text("# Readme\n\nSome *markdown*.\n")
    (server.repo / "logo.bin").write_bytes(b"\x00\x01\x02" * 100)
    spec = server.repo / ".codepilot/specs/demo"
    spec.mkdir(parents=True)
    for doc in ("requirements", "design", "tasks"):
        (spec / f"{doc}.md").write_text(f"# {doc}\n")
    (spec / "spec.json").write_text('{"kind": "feature", "approved": ""}')
    page.set_viewport_size({"width": 1440, "height": 900})
    page.add_init_script("localStorage.getItem('cp--sidebar-w') ?? localStorage.setItem('cp--sidebar-w', '284px')")
    open_app(page)
    show_terminal(page)


def show_terminal(page):
    page.click("#togglePanel")
    page.click("#terminalTabBtn")
    page.locator("#termSelect option").first.wait_for(state="attached")


def assert_keeps(page, sels, what):
    got = page.evaluate(CHECK, sels)
    for c in got["controls"]:
        assert c["inside"] and c["hit"], f"{what}: {c['s']} is cut off or covered at {editor_width(page)}px: {got}"
        assert c["title"] or c["s"] == "#termSelect", f"{what}: {c['s']} has no tooltip"
    assert got["overflow"] <= 0, f"{what}: the bar overflows by {got['overflow']}px"
    return got


@pytest.mark.parametrize("width", [MARKDOWN_AT + 1, MARKDOWN_AT - 1, LABELS_AT + 1, LABELS_AT - 1, COMPACT_AT + 1,
                                   COMPACT_AT - 1, 280])
def test_every_editor_toolbar_keeps_its_controls(page, server, session, width):
    setup(page, server)
    for kind, (opener, sels) in BARS.items():
        page.evaluate(opener)
        page.locator(f".ed-bar {sels[-1]}").wait_for()
        drag_editor_to(page, width)
        got = assert_keeps(page, sels, kind)
        words = {c["s"]: c["words"] for c in got["controls"] if c["words"] is not None}
        markdown = kind in ("markdown", "preview")
        for s, shown in words.items():
            switch = s.startswith("[data-view-mode")
            expected = width > COMPACT_AT if switch else width > (MARKDOWN_AT if markdown else LABELS_AT)
            assert shown == expected, f"{kind} at {width}px: {s} {'shows' if shown else 'hides'} its words"
        if kind in ("file", "markdown"):
            assert got["count"] == (width > (MARKDOWN_AT if markdown else COMPACT_AT)), f"{kind} at {width}: line count"


@pytest.mark.parametrize("width", [TERMINAL_AT + 1, TERMINAL_AT - 1, 280])
def test_the_terminal_toolbar_keeps_its_controls(page, server, session, width):
    setup(page, server)
    drag_editor_to(page, width)
    got = assert_keeps(page, TERMINAL, "terminal")
    assert got["controls"][1]["words"] == (width > TERMINAL_AT)


def test_the_panel_tabs_keep_each_count_beside_its_label(page, server, session):
    setup(page, server)
    drag_editor_to(page, 280)
    lines = page.evaluate("""() => [...document.querySelectorAll('.panel-tabs > button[data-ptab]')].map((b) => {
      const text = document.createRange(); text.selectNodeContents(b.firstChild);
      const t = text.getBoundingClientRect(), c = b.querySelector('.count:not([hidden])')?.getBoundingClientRect();
      return { tab: b.dataset.ptab, wrapped: text.getClientRects().length > 1 || (c && c.top >= t.bottom - 1) }; })""")
    assert not any(t["wrapped"] for t in lines), lines
    for sel in ("#clearActivity", "#closePanel"):  # the row scrolls sideways rather than wrap; these stay reachable
        page.locator(sel).scroll_into_view_if_needed()
        assert page.evaluate("""(s) => { const r = document.querySelector(s).getBoundingClientRect();
          return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)?.closest(s) !== null; }""", sel)


def test_at_a_laptop_size_every_toolbar_button_is_on_screen_with_a_tooltip(page, server, session):
    page.set_viewport_size({"width": 1024, "height": 700})
    open_app(page)
    show_terminal(page)
    page.evaluate("openFile('agent/core.py')")
    page.locator("#fEdit").wait_for()
    assert_keeps(page, BARS["file"][1], "file")
    assert_keeps(page, TERMINAL, "terminal")
    assert page.get_by_role("button", name="Add to chat").count() == 1  # the words still name the button
    assert page.get_by_role("button", name="Selection → chat").count() == 1


# The Review tab: side by side, the change list takes up to 280px; in a narrower editor it sits above the diff.
REVIEW_STACKS_AT = 640  # app.css: the editor's width at or under which the list goes above the diff

REVIEW = """() => {
  const box = (el) => { const r = el.getBoundingClientRect();
    return { l: r.left, r: r.right, t: r.top, b: r.bottom, h: r.height }; };
  const list = document.querySelector('.rv-list'), main = document.querySelector('.rv-main');
  const head = main.querySelector('.ed-bar'), h = head.getBoundingClientRect();
  const acts = ['[data-apply]', '[data-reject]', '#rvOpen'].map((s) => {
    const r = head.querySelector(s).getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return { s, ok: r.left >= h.left - 0.5 && r.right <= h.right + 0.5 && r.top >= h.top - 0.5
                    && r.bottom <= h.bottom + 0.5 && !!hit && head.querySelector(s).contains(hit) };
  });
  return { list: box(list), main: box(main), diff: box(main.querySelector('.ed-scroll')), acts };
}"""


def open_review_with_two_changes(page):
    page.fill("#input", "fix two")
    page.press("#input", "Enter")
    page.click("#rbReview")
    page.locator(".review .rv-item.on").wait_for()
    page.wait_for_function("() => document.querySelectorAll('.review .rv-item').length === 2")


def assert_stacked(page, stacked):
    g = page.evaluate(REVIEW)
    assert all(a["ok"] for a in g["acts"]), f"Apply, Reject or Open file is outside the header or covered: {g}"
    if stacked:
        assert g["list"]["b"] <= g["main"]["t"] + 0.5, f"the change list isn't above the diff: {g}"
        assert g["list"]["h"] < g["diff"]["h"], f"the list takes more height than the diff: {g}"
    else:
        assert g["list"]["r"] <= g["main"]["l"] + 0.5, f"the change list isn't beside the diff: {g}"


def test_in_a_laptop_window_the_review_list_sits_above_the_diff(page, server, session):
    page.set_viewport_size({"width": 1024, "height": 700})
    open_app(page)
    page.click("#togglePanel")  # the bottom panel open too: the Review has the least height
    open_review_with_two_changes(page)
    assert_stacked(page, True)
    first = page.locator(".rv-item.on").get_attribute("data-rv")
    page.keyboard.press("j")
    page.wait_for_function(f"() => document.querySelector('.rv-item.on').dataset.rv !== '{first}'")
    assert_stacked(page, True)
    page.keyboard.press("k")
    page.wait_for_function(f"() => document.querySelector('.rv-item.on').dataset.rv === '{first}'")


@pytest.mark.parametrize("width", [REVIEW_STACKS_AT + 1, REVIEW_STACKS_AT])
def test_the_review_list_moves_above_the_diff_at_a_set_editor_width(page, server, session, width):
    page.set_viewport_size({"width": 1440, "height": 900})
    chat = 1440 - 56 - 280 - width  # the window, less the activity bar, the two resizers and the sidebar
    page.add_init_script(f"localStorage.setItem('cp--sidebar-w', '280px');"
                         f"localStorage.setItem('cp--chat-w', '{chat}px')")
    open_app(page)
    assert abs(editor_width(page) - width) < 0.6
    open_review_with_two_changes(page)
    assert_stacked(page, width <= REVIEW_STACKS_AT)
