"""`codepilot smoke` against a scripted model: what passes and what fails."""

from fakes import FakeLLM, tool_use

from codepilot import images, smoke


def test_red_square_is_a_valid_png():
    assert images.sniff(smoke.red_square()) == "png"


def test_smoke_passes_with_a_capable_model(cfg):
    llm = FakeLLM([
        [tool_use("t1", "read_file", path="calc.py")],
        [tool_use("t2", "propose_edit", path="calc.py", old_text="a - b", new_text="a + b")],
        [{"text": "Proposed the fix."}],
        [{"text": "Red."}],
    ])
    out = []
    assert smoke.run(cfg, progress=out.append, llm=llm) == 0
    assert "smoke test passed" in out[-1] and any("reads images" in o and "pass" in o for o in out)


def test_smoke_fails_when_the_model_skips_tools(cfg):
    llm = FakeLLM([[{"text": "Just change it to a + b."}], [{"text": "Blue"}]])
    out = []
    assert smoke.run(cfg, progress=out.append, llm=llm) == 1
    assert any("tool calls" in o and "FAIL" in o for o in out) and any("reads images" in o and "warn" in o for o in out)
