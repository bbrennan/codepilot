"""The cost meter: dollars as they accrue, an estimate before a long run, and the optional daily cap."""

from dataclasses import replace

from uihelpers import open_app


def wait_idle(page):
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden")


def send(page, text):
    page.fill("#input", text)
    page.press("#input", "Enter")
    page.locator(".msg.user", has_text=text).last.wait_for()
    wait_idle(page)


def with_prices(server):
    server.cfg.home.mkdir(parents=True, exist_ok=True)
    (server.cfg.home / "prices.toml").write_text('["claude-sonnet-5-5"]\ninput = 100.0\noutput = 100.0\n')


def with_budget(server, limit):
    server.agent.cfg = replace(server.agent.cfg, daily_budget=limit)
    server.agent.spend.cfg = server.agent.cfg


def test_the_status_bar_and_memory_show_dollars(page, server, session):
    with_prices(server)
    open_app(page)
    send(page, "hello")
    page.wait_for_function("() => document.querySelector('#sbTokens').textContent.includes('$')")
    bar = page.locator("#sbTokens")
    assert "tokens · $" in bar.text_content()
    tip = bar.get_attribute("title")
    assert "claude-sonnet-5-5" in tip and "Today: $" in tip
    assert "· $" in page.locator(".act", has_text="anthropic.claude-sonnet-5-5").first.text_content()
    page.click("[data-view=memory]")
    table = page.locator("#usageTable")
    table.locator("text=Today").wait_for()
    assert "· $" in table.text_content()


def test_without_prices_it_says_how_to_add_them(page, server, session):
    open_app(page)
    send(page, "hello")
    assert "$" not in page.locator("#sbTokens").text_content()
    page.click("[data-view=memory]")
    page.locator("#usageTable", has_text="prices.example.toml").wait_for()


def test_an_unpriced_model_shows_as_unknown_not_free(page, server, session):
    server.cfg.home.mkdir(parents=True, exist_ok=True)
    (server.cfg.home / "prices.toml").write_text('["some-other-model"]\ninput = 1.0\n')
    open_app(page)
    send(page, "hello")
    page.wait_for_function("() => document.querySelector('#sbTokens').textContent.includes('$?')")
    assert "No price" in page.locator("#sbTokens").get_attribute("title")


def test_the_daily_budget_stops_and_can_be_lifted(page, server, session):
    with_prices(server)
    with_budget(server, 0.000001)
    open_app(page)
    send(page, "hello")  # the first call spends past the cap
    send(page, "and again")
    banner = page.locator(".banner.budget")
    banner.wait_for()
    assert "Daily budget reached" in banner.text_content()
    before = len(server.llm.calls)
    banner.locator("[data-budget-continue]").click()
    page.locator(".toast", has_text="until midnight").wait_for()
    assert len(server.llm.calls) == before  # lifting the cap sends nothing by itself
    send(page, "carry on")
    assert len(server.llm.calls) == before + 1


def _spec_with_tasks(page, server):
    """A spec at the Implement step with three tasks, the first one done through the UI."""
    spec = server.repo / ".codepilot/specs/demo"
    spec.mkdir(parents=True)
    (spec / "requirements.md").write_text("# R\n")
    (spec / "design.md").write_text("# D\n")
    (spec / "tasks.md").write_text("- [ ] 1. One\n- [ ] 2. Two\n- [ ] 3. Three\n")
    (spec / "spec.json").write_text('{"kind": "feature", "approved": "tasks"}')
    open_app(page)
    page.click("[data-view=specs]")
    page.locator("[data-spec-open=demo]").click()
    page.locator("#spNext").click()
    page.locator(".sp-task.done").wait_for()
    wait_idle(page)


def test_run_all_remaining_estimates_from_tasks_already_run(page, server, session):
    with_prices(server)
    _spec_with_tasks(page, server)
    page.click("#spAll")
    page.locator("#dialogTitle", has_text="Run all remaining?").wait_for()
    hint = page.locator("#dialogHint").text_content()
    assert "for 2 tasks" in hint and "average of the last 1 task" in hint and hint.startswith("About $")
    page.click("#dialogCancel")
    assert page.locator("#dialog").is_hidden() and page.locator(".sp-task.done").count() == 1


def test_run_all_remaining_just_runs_when_there_is_no_estimate(page, server, session):
    _spec_with_tasks(page, server)  # no prices, so no estimate
    page.click("#spAll")
    page.wait_for_function("() => document.querySelectorAll('.sp-task.done').length === 3")
