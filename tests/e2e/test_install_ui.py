"""codepilot can be installed as an app (Chrome or Edge: Install), with its own name, icon, window and Dock icon. Asked
of the browser itself: Chromium reports the manifest it found and what it made of it. (Chrome installs almost any page
as a bare shortcut, so "installable" alone proves little: the manifest is what gives it a name, icon and window.)"""

import json

from uihelpers import open_app


def test_the_browser_finds_codepilots_app_manifest(page, server, session):
    open_app(page)
    cdp = page.context.new_cdp_session(page)
    found = cdp.send("Page.getAppManifest")
    assert found["url"].endswith("/static/manifest.webmanifest"), found
    assert found["errors"] == [], found["errors"]
    manifest = json.loads(found["data"])
    assert manifest["name"] == "Codepilot" and manifest["display"] == "standalone" and manifest["start_url"] == "/"
    for icon in manifest["icons"]:  # every icon it names is really there, as an image
        resp = page.request.get(icon["src"])
        assert resp.ok and resp.headers["content-type"].startswith("image/"), icon
    assert cdp.send("Page.getInstallabilityErrors")["installabilityErrors"] == []


# The colour the installed window's title bar uses: the theme-color whose media query applies.
TITLE_BAR = """() => [...document.querySelectorAll('meta[name="theme-color"]')]
  .find((m) => matchMedia(m.media || 'all').matches)?.content"""


def test_the_title_bar_follows_the_theme_you_picked_not_only_the_system(page, server, session):
    page.emulate_media(color_scheme="light")
    open_app(page)
    assert page.evaluate(TITLE_BAR) == "#e9ecf1"  # nothing picked: the system's (light)
    page.click("#themeBtn")  # pick dark
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert page.evaluate(TITLE_BAR) == "#0d0f13"
    page.reload()
    page.wait_for_function("() => document.querySelector('#sbProvider')?.textContent.length > 0")
    assert page.evaluate(TITLE_BAR) == "#0d0f13"  # still dark after a reload
