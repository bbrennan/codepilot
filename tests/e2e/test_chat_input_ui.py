"""Getting things into the chat: pasting text and images, attaching files, image links, and carrying on
automatically after you review changes."""

import base64
import http.server
import sys
import threading

import pytest
from uihelpers import open_app

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9a"
                       "wAAAABJRU5ErkJggg==")
PNG_B64 = base64.b64encode(PNG).decode()


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def model_calls(server):
    return [c for c in server.llm.calls if "messages" in c]


def sent_images(call):
    return sum(1 for b in call["messages"][-1]["content"] if "image" in b)


PASTE_IMAGE = """(b64) => {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const dt = new DataTransfer();
  dt.items.add(new File([bytes], "shot.png", { type: "image/png" }));
  const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
  document.querySelector('#input').dispatchEvent(ev);
}"""


def test_paste_an_image_and_send_it(page, server, session):
    open_app(page)
    page.click("#input")
    page.evaluate(PASTE_IMAGE, PNG_B64)
    page.locator("#attachTray img").wait_for()
    page.fill("#input", "what is in this screenshot?")
    page.press("#input", "Enter")
    page.locator("#transcript .img-row img").wait_for()
    wait_idle(page)
    assert page.locator("#attachTray").is_hidden()
    assert sent_images(model_calls(server)[-1]) == 1
    page.reload()  # images are part of the stored conversation
    page.locator("#transcript .img-row img").wait_for()


def test_attach_button_and_image_only_message(page, server, session, tmp_path):
    shot = tmp_path / "ui.png"
    shot.write_bytes(PNG)
    open_app(page)
    page.set_input_files("#imgFile", str(shot))
    page.locator("#attachTray img").wait_for()
    page.locator("#attachTray [data-unattach]").click()  # remove it again
    assert page.locator("#attachTray").is_hidden()
    page.set_input_files("#imgFile", str(shot))
    page.locator("#attachTray img").wait_for()
    page.press("#input", "Enter")  # no text: the image alone is enough
    page.locator(".msg.user", has_text="(see the attached image)").wait_for()
    wait_idle(page)
    assert sent_images(model_calls(server)[-1]) == 1


def test_text_paste_still_works(page, server, session):
    open_app(page)
    page.click("#input")
    page.evaluate("""() => { const dt = new DataTransfer(); dt.setData('text/plain', 'pasted words');
      const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
      document.querySelector('#input').dispatchEvent(ev); }""")
    page.keyboard.type("typed")  # a text paste isn't intercepted (the browser inserts it natively)
    assert page.locator("#attachTray").is_hidden()


@pytest.mark.skipif(sys.platform != "darwin", reason="Ctrl+V as paste is a macOS convenience")
def test_ctrl_v_pastes_on_a_mac(page, server, session):
    open_app(page)
    page.click("#input")
    page.evaluate("() => navigator.clipboard.writeText('from the clipboard')")
    page.keyboard.press("Control+v")
    page.wait_for_function("() => document.querySelector('#input').value === 'from the clipboard'")


@pytest.mark.skipif(sys.platform != "darwin", reason="Ctrl+V as paste is a macOS convenience")
def test_ctrl_v_works_in_other_text_boxes_too(page, server, session):
    open_app(page)
    page.evaluate("() => navigator.clipboard.writeText('core.py')")
    page.keyboard.press("Meta+p")
    page.locator("#paletteInput").wait_for()
    page.keyboard.press("Control+v")
    page.wait_for_function("() => document.querySelector('#paletteInput').value === 'core.py'")


@pytest.mark.skipif(sys.platform != "darwin", reason="Ctrl+V as paste is a macOS convenience")
def test_ctrl_v_says_how_to_fix_a_blocked_clipboard(page, server, session):
    open_app(page)
    page.context.clear_permissions()  # like a browser where clipboard access was blocked
    page.click("#input")
    page.keyboard.press("Control+v")
    msg = page.locator(".toast", has_text="Ctrl+V couldn't read the clipboard")
    msg.wait_for()
    assert "⌘V always works" in msg.text_content() and "chrome://settings/content/clipboard" in msg.text_content()
    assert any("Ctrl+V paste" in e for e in page.evaluate("() => pageErrors"))  # so a problem report shows it


def test_image_link_in_a_message_is_attached(page, server, session):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(PNG)

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        open_app(page)
        url = f"http://127.0.0.1:{httpd.server_address[1]}/screens/login.png"
        page.fill("#input", f"why does {url} look broken?")
        page.press("#input", "Enter")
        page.locator("#transcript .img-row img").wait_for()
        wait_idle(page)
        assert sent_images(model_calls(server)[-1]) == 1
    finally:
        httpd.shutdown()


def test_applying_the_changes_resumes_on_its_own(page, server, session):
    open_app(page)
    page.fill("#input", "fix two things")
    page.press("#input", "Enter")
    page.locator("#rbApplyAll").wait_for()
    wait_idle(page)
    before = len(model_calls(server))
    page.click("#rbApplyAll")
    page.locator(".wait-row", has_text="Continuing after your review").wait_for()
    wait_idle(page)
    calls = model_calls(server)
    assert len(calls) == before + 1 and "I've reviewed your proposed changes" in str(calls[-1]["messages"][-1])
    assert "was applied" in str(calls[-1]["messages"][-1])  # the turn context reports each outcome
    page.reload()
    page.locator(".wait-row", has_text="Continued after your review").wait_for()


def test_rejecting_everything_waits_for_you(page, server, session):
    open_app(page)
    page.fill("#input", "fix the add bug")
    page.press("#input", "Enter")
    page.locator("#rbRejectAll").wait_for()
    wait_idle(page)
    before = len(model_calls(server))
    page.click("#rbRejectAll")
    page.wait_for_function("() => document.querySelector('#reviewBar').hidden")
    page.wait_for_timeout(500)
    assert len(model_calls(server)) == before
