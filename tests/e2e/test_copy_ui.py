"""Words on screen read cleanly: no stutters, no mangled paths, no paragraphs of explanation in the way, no buttons cut
off at the side."""

import pytest
from test_files_ui import menu
from uihelpers import open_app


def test_a_modes_placeholder_doesnt_repeat_its_name(page, server, session):
    open_app(page)
    page.select_option("#modeSelect", "spec")
    placeholder = page.locator("#input").get_attribute("placeholder")
    assert not placeholder.lower().startswith("spec: spec"), placeholder
    page.select_option("#modeSelect", "plan")
    assert page.locator("#input").get_attribute("placeholder").startswith("Plan")  # still names the mode


def test_steering_headers_keep_paths_as_written(page, server, session):
    open_app(page)
    page.click("[data-view=steering]")
    page.locator("#steeringView .group-head", has_text="workspace").first.wait_for()
    shown = page.locator("#steeringView").inner_text()  # as displayed, after any text-transform
    assert ".codepilot/steering" in shown and ".CODEPILOT/STEERING" not in shown


def test_the_memory_view_is_compact_and_nothing_is_cut_off(page, server, session):
    open_app(page)
    page.click("[data-view=memory]")
    page.locator("#handoffBtn").wait_for()
    how = page.locator("#memoryView details", has_text="How memory works")
    assert how.count() == 1 and how.get_attribute("open") is None  # the explanation is there, folded away
    sidebar = page.locator(".sidebar").bounding_box()
    for sel in ("#compactBtn", "#handoffBtn"):
        box = page.locator(sel).bounding_box()
        assert box["x"] + box["width"] <= sidebar["x"] + sidebar["width"] + 0.5, f"{sel} is cut off"
    assert page.evaluate("() => tilde(state.cfg.home + '/.codepilot/notes/x.md')") == "~/.codepilot/notes/x.md"
    page.locator("#notesPath[title]").wait_for(state="attached")  # the full path, on hover


def test_a_one_line_file_says_1_line(page, server, session):
    (server.repo / "one.txt").write_text("just one line\n")
    open_app(page)
    page.click("#tree [data-file='one.txt']")
    page.locator("#editor code", has_text="just one line").wait_for()
    assert page.locator("#editor .ed-bar .muted").first.text_content() == "1 line"


# Every shortcut shown, written one way per platform. (navigator.platform decides, as it does for the key handlers.)
KEYS = {
    "mac": {"welcome": ["⌃`", "⌘P", "⌘B", "⌘J", "⌘L", "⌥W", "@"], "file": ["⌘P", "⌥W"], "explorer": ["⌘C", "F2", "⌘⌫"],
            "stop": "⌘.", "steer": "⌘Enter"},
    "other": {"welcome": ["Ctrl+`", "Ctrl+P", "Ctrl+B", "Ctrl+J", "Ctrl+L", "Alt+W", "@"], "file": ["Ctrl+P", "Alt+W"],
              "explorer": ["Ctrl+C", "F2", "Delete"], "stop": "Ctrl+.", "steer": "Ctrl+Enter"},
}


@pytest.mark.parametrize("platform, platform_name", [("mac", "MacIntel"), ("other", "Linux x86_64")])
def test_shortcuts_are_written_one_way_per_platform(page, server, session, platform, platform_name):
    page.add_init_script(f"Object.defineProperty(navigator, 'platform', {{ get: () => '{platform_name}' }})")
    want = KEYS[platform]
    open_app(page)
    assert page.locator("#editor .kbd-grid kbd").all_text_contents() == want["welcome"]
    assert want["stop"] in page.get_attribute("#stopBtn", "title")
    assert want["steer"] in page.get_attribute("#steerBtn", "title")
    page.click("#tree [data-dir='agent']")
    page.click("#tree [data-file='agent/core.py']")
    page.click("#fileMenuBtn")
    assert page.locator("#ctxMenu .mi kbd").all_text_contents() == want["file"]
    page.keyboard.press("Escape")
    page.locator("#tree [data-file='agent/core.py']").click(button="right")
    assert page.locator("#ctxMenu .mi kbd").all_text_contents() == want["explorer"]


def test_a_stopped_turn_reads_stopped_live_and_after_a_reload(page, server, session):
    open_app(page)
    page.fill("#input", "be very slow")
    page.press("#input", "Enter")
    page.locator(".msg.assistant", has_text="Thinking").wait_for()
    page.click("#stopBtn")
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")
    live = page.locator("#transcript .msg.assistant").last
    assert live.locator("em", has_text="(stopped)").count() == 1, live.inner_html()
    assert page.locator("#transcript .banner", has_text="Stopped").count() == 0
    page.reload()
    page.locator("#transcript .msg.assistant").first.wait_for()
    assert page.locator("#transcript .msg.assistant").last.locator("em", has_text="(stopped)").count() == 1


def test_the_folder_dialog_says_add_when_it_adds_a_folder(page, server, session):
    open_app(page)
    page.click("#workspaceBtn")
    menu(page, "Add folder…")
    page.locator("#folderDialog").wait_for()
    assert page.locator("#folderDialog .fd-head b").text_content() == "Add folder"
    page.wait_for_function("() => document.querySelector('#fdOpen').textContent === 'Add this folder'")
    page.click("#fdCancel")


# The small layout slips: spacing, alignment, wrapping.
def test_the_github_item_is_spaced_like_its_neighbours(page, server, session):
    open_app(page)
    gap = page.evaluate("""() => { const el = document.querySelector('#sbGithub'), svg = el.querySelector('svg');
      const text = [...el.querySelectorAll('*'), el].flatMap((n) => [...n.childNodes]).find((n) => n.nodeType === 3 && n.textContent.trim());
      const r = document.createRange(); r.selectNodeContents(text);
      return r.getBoundingClientRect().left - svg.getBoundingClientRect().right; }""")
    assert gap >= 5, f"the GitHub icon touches its text ({gap}px)"


def test_search_hit_line_numbers_line_up(page, server, session):
    (server.repo / "long.py").write_text("".join(("needle = 1\n" if i in (7, 120) else f"x{i} = 0\n") for i in range(1, 130)))
    open_app(page)
    page.click("[data-view=search]")
    page.fill("#grepInput", "needle")
    page.press("#grepInput", "Enter")
    page.locator(".grep-hit[data-gline='120']").wait_for()
    rights = page.evaluate("() => [...document.querySelectorAll('.grep-hit[data-gpath=\"long.py\"] b')].map((b) => b.getBoundingClientRect().right)")
    assert len(rights) == 2 and abs(rights[0] - rights[1]) < 0.5, rights


def test_a_long_notes_path_wraps_inside_the_sidebar(page, server, session):
    open_app(page)
    page.click("[data-view=memory]")
    page.locator("#notesPath[title]").wait_for(state="attached")
    page.evaluate("() => { document.querySelector('#notesPath').textContent = '~/' + 'a-very-long-folder-name/'.repeat(8) + 'notes.md'; }")
    fits = page.evaluate("() => document.querySelector('#notesPath').getBoundingClientRect().right <= document.querySelector('.sidebar').getBoundingClientRect().right + 0.5")
    shown = page.evaluate("() => { const el = document.querySelector('#notesPath'); return el.scrollWidth <= el.clientWidth + 1; }")
    assert fits and shown, "the notes path runs under the sidebar's edge or is cut off"
