"""Dragging files from the desktop into the explorer adds them to the workspace."""

DROP = """([selector, files]) => {
  const dt = new DataTransfer();
  for (const f of files) dt.items.add(new File([new Uint8Array(f.bytes)], f.name, { type: f.type || "" }));
  const target = document.querySelector(selector);
  for (const type of ["dragenter", "dragover", "drop"]) {
    target.dispatchEvent(new DragEvent(type, { dataTransfer: dt, bubbles: true, cancelable: true }));
  }
  return window.__lastDropPrevented;
}"""


def drop(page, selector, *files):
    return page.evaluate(DROP, [selector, [{"name": n, "bytes": list(b), "type": ""} for n, b in files]])


def test_drop_on_the_empty_area_adds_to_the_workspace_root(page, server, session):
    from uihelpers import open_app
    open_app(page)
    drop(page, "#tree", ("notes.txt", b"hello"), ("blob.bin", bytes(range(200))))
    page.locator("#tree [data-file='notes.txt']").wait_for()
    assert (server.repo / "notes.txt").read_text() == "hello"
    assert (server.repo / "blob.bin").read_bytes() == bytes(range(200))
    page.locator(".toast", has_text="Added 2 files").wait_for()


def test_drop_on_a_folder_goes_into_that_folder_and_on_a_file_into_its_folder(page, server, session):
    from uihelpers import open_app
    open_app(page)
    page.click("#tree [data-dir='agent']")
    page.locator("#tree [data-file='agent/core.py']").wait_for()
    drop(page, "#tree [data-dir='agent']", ("into_dir.txt", b"1"))
    page.locator("#tree [data-file='agent/into_dir.txt']").wait_for()
    drop(page, "#tree [data-file='agent/core.py']", ("beside.txt", b"2"))
    page.locator("#tree [data-file='agent/beside.txt']").wait_for()
    assert (server.repo / "agent/into_dir.txt").exists() and (server.repo / "agent/beside.txt").exists()


def test_an_existing_file_asks_before_it_is_replaced(page, server, session):
    from uihelpers import open_app
    (server.repo / "keep.txt").write_text("mine")
    page.expected_errors.append("409")  # the server's "already exists" answer, which is what triggers the question
    open_app(page)
    drop(page, "#tree", ("keep.txt", b"theirs"))
    page.locator("#dialog", has_text="keep.txt").wait_for()
    page.click("#dialogCancel") if page.locator("#dialogCancel").count() else page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert (server.repo / "keep.txt").read_text() == "mine"
    drop(page, "#tree", ("keep.txt", b"theirs"))
    page.locator("#dialogOk").wait_for()
    page.click("#dialogOk")
    page.wait_for_function("() => document.querySelector('.toast')?.textContent.includes('Added 1 file')")
    assert (server.repo / "keep.txt").read_text() == "theirs"


def test_dropping_a_file_anywhere_never_navigates_away_from_codepilot(page, server, session):
    from uihelpers import open_app
    open_app(page)
    url = page.url
    prevented = page.evaluate("""() => {
      const dt = new DataTransfer(); dt.items.add(new File(["x"], "stray.txt"));
      const ev = new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true });
      document.querySelector("#editor").dispatchEvent(ev);
      return ev.defaultPrevented; }""")
    assert prevented and page.url == url


def test_files_go_to_the_workspace_they_were_dropped_on_even_if_the_session_changes_midway(page, server, session):
    from uihelpers import open_app
    open_app(page)
    seen = []

    def hold_first(route):
        seen.append(route.request.url)
        if len(seen) == 1:
            page.evaluate("state.sid = 'some-other-session'")  # the user switches session while the first PUT is in flight
        route.continue_()

    page.route("**/upload?*", hold_first)
    drop(page, "#tree", ("one.txt", b"1"), ("two.txt", b"2"), ("three.txt", b"3"))
    page.wait_for_function("() => document.querySelectorAll('.toast').length > 0")
    page.wait_for_timeout(500)
    assert len(seen) == 3 and all(f"/api/sessions/{session.id}/upload" in u for u in seen), seen
    assert all((server.repo / n).exists() for n in ("one.txt", "two.txt", "three.txt"))
