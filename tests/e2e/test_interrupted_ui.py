"""A step interrupted by a restart (its call stored, its result never) doesn't spin forever or break the chat: its card
says it didn't run, and the next message works."""

from uihelpers import open_app


def interrupted(server):
    sess = server.store.create_session(str(server.repo), "main")
    server.store.add_message(sess.id, "user", [{"text": "run the long build"}])
    server.store.add_message(sess.id, "assistant", [
        {"text": "Building."}, {"toolUse": {"toolUseId": "t1", "name": "run_command", "input": {"command": "make all"}}}])
    return sess


def test_an_interrupted_step_shows_as_not_run_and_the_chat_carries_on(page, server):
    interrupted(server)
    open_app(page)
    card = page.locator("details.tool", has_text="run_command")
    card.wait_for()
    assert card.locator(".spinner").count() == 0 and card.locator(".st.err").count() == 1
    page.fill("#input", "what happened?")
    page.press("#input", "Enter")
    page.wait_for_function("() => document.querySelector('#stopBtn').hidden", timeout=20_000)
    assert page.locator(".msg.assistant").last.inner_text().strip()  # the model answered: the session isn't stuck
    assert page.locator(".banner.error, .msg.error").count() == 0
    assert page.locator("details.tool .spinner").count() == 0
