"""Words on screen read cleanly: no stutters, no mangled paths, no paragraphs of explanation in the way, no buttons cut
off at the side."""

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
