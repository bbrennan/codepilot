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
