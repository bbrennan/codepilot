"""The layout holds still: the message box stays on screen whatever piles up above it (a long command waiting
for approval, the plan, queued messages, images, a long draft), on short laptop screens too, and nothing jiggles
when the explorer re-renders."""

import base64

import pytest

from uihelpers import open_app

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

# Every animation frame: is the message box fully inside the window and above the status bar?
WATCH = """() => {
  window.__off = [];
  const tick = () => {
    const r = document.querySelector('#composerBox').getBoundingClientRect();
    const limit = Math.min(innerHeight, document.querySelector('.statusbar').getBoundingClientRect().top);
    if (r.top < 0 || r.bottom > limit + 0.5 || r.height < 40) window.__off.push({ top: r.top, bottom: r.bottom, limit, h: r.height });
    window.__raf = requestAnimationFrame(tick);
  };
  tick();
}"""


def in_view(page, selector):
    return page.evaluate("""(sel) => { const r = document.querySelector(sel).getBoundingClientRect();
      const limit = Math.min(innerHeight, document.querySelector('.statusbar').getBoundingClientRect().top);
      return r.height > 0 && r.top >= 0 && r.bottom <= limit + 0.5; }""", selector)


@pytest.mark.parametrize("size", [(1440, 900), (1280, 720), (1280, 620), (1024, 520)])
def test_the_message_box_stays_on_screen_while_everything_piles_up(page, server, session, tmp_path, size):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    open_app(page)
    page.evaluate(WATCH)
    page.fill("#input", "be slow")
    page.press("#input", "Enter")
    page.locator(".msg.assistant", has_text="Thinking").wait_for()
    for text in ["queued one", "queued two", "queued three"]:
        page.fill("#input", text)
        page.press("#input", "Enter")
    page.wait_for_function("() => document.querySelectorAll('.msg.queued').length === 3")
    (tmp_path / "shot.png").write_bytes(PNG)
    page.set_input_files("#imgFile", str(tmp_path / "shot.png"))
    page.locator("#attachTray img").wait_for()
    page.fill("#input", "\n".join(f"a long draft, line {i}" for i in range(20)))
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden", timeout=30_000)
    page.click("#attachTray [data-unattach]")
    page.fill("#input", "a long command please")
    page.press("#input", "Enter")
    page.locator("#reviewBar .rb-approval").wait_for()
    page.locator("#plan:not([hidden])").wait_for()
    page.fill("#input", "\n".join(f"another long draft, line {i}" for i in range(20)))
    page.wait_for_timeout(300)
    off = page.evaluate("() => (cancelAnimationFrame(window.__raf), window.__off)")
    assert not off, f"the message box left the screen in {len(off)} frames, e.g. {off[:3]}"
    assert in_view(page, "#composerBox") and in_view(page, "#rbApprove") and in_view(page, "#rbDeny")
    assert page.evaluate("document.querySelector('#transcript').clientHeight") >= 60  # the conversation keeps a view
    cmd = page.locator("#reviewBar .rb-cmd")
    assert cmd.evaluate("e => e.scrollHeight > e.clientHeight")  # the long command scrolls inside the bar
    page.press("#input", "ControlOrMeta+a")
    page.press("#input", "Delete")
    page.click("#rbApprove")


def test_typing_a_long_message_while_it_works_keeps_the_chat_following(page, server, session):
    page.set_viewport_size({"width": 1280, "height": 720})
    open_app(page)
    for _ in range(3):  # enough conversation to scroll
        page.fill("#input", "hello")
        page.press("#input", "Enter")
        page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    page.fill("#input", "be slow")
    page.press("#input", "Enter")
    page.locator(".msg.assistant", has_text="Thinking").wait_for()
    page.fill("#input", "\n".join(f"a long follow-up, line {i}" for i in range(12)))  # the message box grows
    page.wait_for_timeout(600)  # more of the reply streams in
    gap = page.evaluate("(() => { const t = document.querySelector('#transcript'); return t.scrollHeight - t.scrollTop - t.clientHeight; })()")
    assert page.evaluate("(() => { const t = document.querySelector('#transcript'); return t.scrollHeight > t.clientHeight + 100; })()")
    assert gap < 5, f"the chat stopped following the reply ({gap}px from the bottom)"
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden", timeout=30_000)


def test_hovering_an_explorer_row_does_not_move_the_rows_below(page, server, session):
    open_app(page)
    rows = page.locator("#tree .row")
    below = rows.nth(rows.count() - 1)
    y = below.bounding_box()["y"]
    rows.first.hover()  # shows its hover buttons
    page.locator("#tree .row:hover .hover-act").first.wait_for()
    assert below.bounding_box()["y"] == y


def pile_up(page, tmp_path, n_images=8):
    """A plan, a long command waiting for approval, a long draft, and several attached images, on a short window."""
    open_app(page)
    page.fill("#input", "a long command please")
    page.press("#input", "Enter")
    page.locator("#reviewBar .rb-approval").wait_for()
    page.locator("#plan:not([hidden])").wait_for()
    (tmp_path / "shot.png").write_bytes(PNG)
    for _ in range(n_images):
        page.set_input_files("#imgFile", str(tmp_path / "shot.png"))
    page.wait_for_function(f"() => document.querySelectorAll('#attachTray img').length >= {n_images}")
    page.fill("#input", "\n".join(f"draft line {i}" for i in range(20)))


def test_the_mention_popup_and_the_attachment_tray_stay_usable_on_a_short_window(page, server, session, tmp_path):
    page.set_viewport_size({"width": 1024, "height": 520})
    pile_up(page, tmp_path)
    assert in_view(page, "#composerBox") and in_view(page, "#rbApprove")
    tray = page.locator("#attachTray")
    assert tray.evaluate("e => e.scrollHeight <= e.clientHeight || getComputedStyle(e).overflowY !== 'visible'")
    page.fill("#input", "@")
    page.locator(".mention-pop .opt").first.wait_for()
    hit = page.evaluate("""() => { const r = document.querySelector('.mention-pop .opt').getBoundingClientRect();
      const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return { top: r.top, inPopup: !!el?.closest('.mention-pop') }; }""")
    assert hit["top"] >= 0 and hit["inPopup"], f"the first suggestion is cut off or covered: {hit}"


def start_slow_turn(page):
    page.set_viewport_size({"width": 1280, "height": 560})  # short enough that the conversation scrolls
    open_app(page)
    for _ in range(6):
        page.fill("#input", "hello")
        page.press("#input", "Enter")
        page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    page.fill("#input", "be slow")
    page.press("#input", "Enter")
    page.locator(".msg.assistant", has_text="Thinking").wait_for()
    assert page.evaluate("(() => { const t = document.querySelector('#transcript'); return t.scrollHeight > t.clientHeight + 100; })()")


def gap(page):
    return page.evaluate("(() => { const t = document.querySelector('#transcript'); return t.scrollHeight - t.scrollTop - t.clientHeight; })()")


def test_a_cancelled_touch_pan_does_not_leave_following_switched_off(page, server, session):
    start_slow_turn(page)
    # a cancelled touch pan never delivers pointerup; "dragging" must not stay on and read later scrolls as the user's
    page.evaluate("""() => { const t = document.querySelector('#transcript');
      t.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
      t.dispatchEvent(new PointerEvent('pointercancel', { bubbles: true })); }""")
    page.fill("#input", "\n".join(f"a long follow-up, line {i}" for i in range(12)))  # the view shrinks: browser-made scrolls
    page.wait_for_timeout(600)
    assert gap(page) < 5, f"following was switched off by browser-made scrolls ({gap(page)}px from the bottom)"


def test_a_scroll_event_queued_as_the_view_shrinks_is_not_mistaken_for_the_user(page, server, session):
    start_slow_turn(page)
    # Just after a touch, scrolls count as the user's for a moment. A scroll event already queued by streaming can
    # then fire after the message box grew but before the ResizeObserver catches up, far from the bottom. Forced in
    # that order here, in one task, so it doesn't depend on timing.
    page.evaluate("""() => { const t = document.querySelector('#transcript');
      t.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
      t.dispatchEvent(new PointerEvent('pointercancel', { bubbles: true }));
      document.querySelector('.composer').style.paddingTop = '200px';
      t.dispatchEvent(new Event('scroll')); }""")
    page.wait_for_timeout(100)
    assert gap(page) < 5, f"following was switched off by a browser-made scroll ({gap(page)}px from the bottom)"


def test_focusing_older_content_stops_the_chat_following(page, server, session):
    start_slow_turn(page)
    # keyboard focus (or Find) scrolling to older content sends no wheel/touch/key event to the transcript
    page.evaluate("""() => { const t = document.querySelector('#transcript');
      t.firstElementChild.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
      t.scrollTop = 0; }""")
    page.wait_for_timeout(600)  # more of the reply streams in
    assert gap(page) > 40, "the next streamed event dragged the view away from what the user focused"


def test_a_streamed_event_landing_before_the_scroll_event_doesnt_undo_the_users_move(page, server, session):
    start_slow_turn(page)
    # The browser delivers a scroll event a frame after the move. A streamed event in that frame used to snap the view
    # straight back, and the scroll event then saw the bottom. Forced in that order here, in one task.
    page.evaluate("""() => { const t = document.querySelector('#transcript');
      t.firstElementChild.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
      t.scrollTop = 0;
      scrollEnd(); }""")
    page.wait_for_timeout(600)  # more of the reply streams in
    assert gap(page) > 40, "the user's move was undone before its scroll event arrived"


def test_toasts_stay_off_the_message_box_when_the_editor_is_narrow(page, server, session):
    page.set_viewport_size({"width": 1024, "height": 700})
    open_app(page)
    page.evaluate("toast('a fairly long notification that would otherwise be centred across the whole window')")
    mine = page.locator(".toast", has_text="fairly long notification")
    mine.wait_for()
    toast, composer = mine.bounding_box(), page.locator("#composerBox").bounding_box()
    editor = page.evaluate("(() => { const r = document.querySelector('.center').getBoundingClientRect(); return { l: r.left, r: r.right }; })()")
    assert toast["x"] >= editor["l"] - 1 and toast["x"] + toast["width"] <= editor["r"] + 1, (toast, editor)
    assert toast["x"] + toast["width"] <= composer["x"] or toast["y"] + toast["height"] <= composer["y"]
