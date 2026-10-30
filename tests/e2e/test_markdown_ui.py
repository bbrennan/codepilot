"""Markdown preview: rendering, safety, links, images, diagrams, and switching to source or editing."""

import base64

from uihelpers import open_app

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9a"
                       "wAAAABJRU5ErkJggg==")
DOC = """---
inclusion: always
---
# Project guide

See [the API notes](docs/api.md) and [setup](#getting-set-up).

| Command | Does |
|---|---|
| `make test` | runs the tests |

- [x] written
- [ ] reviewed

![architecture](docs/arch.png)

```python
def add(a, b):
    return a + b
```

```mermaid
graph LR
  A[Client] --> B[API]
```

## Getting set up

<script>window.__pwned = 1</script>
<img src="x" onerror="window.__pwned = 2">
<a href="javascript:window.__pwned=3">click</a>
"""


def doc_repo(server):
    (server.repo / "docs").mkdir(exist_ok=True)
    (server.repo / "docs" / "arch.png").write_bytes(PNG)
    (server.repo / "docs" / "api.md").write_text("# API notes\n\nGET /orders\n")
    (server.repo / "GUIDE.md").write_text(DOC)


def open_preview(page, path="GUIDE.md"):
    page.locator(f"#tree [data-file='{path}']").click(button="right")
    page.locator("#ctxMenu .mi span", has_text="Open Preview").click()


def test_markdown_opens_as_raw_text_like_vscode(page, server, session):
    doc_repo(server)
    page.expected_errors.append("Failed to load resource")
    open_app(page)
    page.click("#tree [data-file='GUIDE.md']")
    page.locator(".code-view", has_text="# Project guide").wait_for()
    assert page.locator("#docBody").count() == 0  # not rendered
    assert page.locator("[data-view-mode=preview]").count() == 1  # the Preview button is one click away

    page.click("#fEdit")  # the raw text is editable straight away
    assert page.input_value("#codeEdit").startswith("---\ninclusion: always")


def test_open_preview_renders_safely(page, server, session):
    doc_repo(server)
    page.expected_errors.append("Failed to load resource")  # the hostile <img src="x"> 404s
    open_app(page)
    open_preview(page)
    doc = page.locator("#docBody")
    doc.locator("h1", has_text="Project guide").wait_for()
    assert doc.locator("table th", has_text="Command").count() == 1
    assert doc.locator("input[type=checkbox]").count() == 2
    assert "inclusion: always" in doc.locator(".front-matter").text_content()
    assert doc.locator("pre code .hljs-keyword").count() >= 1  # highlighted
    page.wait_for_function("() => document.querySelector('#docBody img[alt=architecture]')?.naturalWidth > 0")
    doc.locator(".mermaid-block svg").wait_for(timeout=20_000)
    assert page.evaluate("window.__pwned") is None
    assert doc.locator("script").count() == 0 and doc.locator("[onerror]").count() == 0
    assert doc.locator("a[href^='javascript']").count() == 0

    doc.locator("a", has_text="the API notes").click()  # a link followed from a preview opens its target in preview
    page.locator("#docBody h1", has_text="API notes").wait_for()


def test_source_toggle_and_draft_preview(page, server, session):
    doc_repo(server)
    page.expected_errors.append("Failed to load resource")
    open_app(page)
    page.click("#tree [data-file='GUIDE.md']")
    page.locator(".code-view", has_text="# Project guide").wait_for()
    page.click("[data-view-mode=preview]")
    page.locator("#docBody h1").wait_for()
    page.click("[data-view-mode=source]")
    page.locator(".code-view", has_text="# Project guide").wait_for()

    page.click("#fEdit")
    page.locator("#codeEdit").fill("# Draft title\n\nSome **bold** text.")
    page.click("#fEditPreview")
    page.locator("#docBody h1", has_text="Draft title").wait_for()
    assert page.locator("#docBody strong", has_text="bold").count() == 1
    page.click("#fEditPreview")  # back to editing, the draft is kept
    assert page.input_value("#codeEdit").startswith("# Draft title")


def test_other_files_have_no_open_preview_item(page, server, session):
    doc_repo(server)
    open_app(page)
    page.click("#tree [data-dir='docs']")
    page.locator("#tree [data-file='docs/arch.png']").click(button="right")
    page.locator("#ctxMenu .mi").first.wait_for()
    assert page.locator("#ctxMenu .mi span", has_text="Open Preview").count() == 0


def test_image_files_open_as_images(page, server, session):
    doc_repo(server)
    open_app(page)
    page.click("#tree [data-dir='docs']")
    page.click("#tree [data-file='docs/arch.png']")
    page.wait_for_function("() => document.querySelector('#imgView')?.naturalWidth > 0")
    assert page.locator("#imgSize").text_content() == "1 × 1"


def test_open_preview_on_a_file_being_edited_shows_the_draft_rendered(page, server, session):
    doc_repo(server)
    page.expected_errors.append("Failed to load resource")
    open_app(page)
    page.click("#tree [data-file='GUIDE.md']")
    page.click("#fEdit")
    page.locator("#codeEdit").fill("# Unsaved draft\n\nbody")
    open_preview(page)
    page.locator("#docBody h1", has_text="Unsaved draft").wait_for()
    page.click("#fEditPreview")  # and back to editing keeps the draft
    assert page.input_value("#codeEdit").startswith("# Unsaved draft")
