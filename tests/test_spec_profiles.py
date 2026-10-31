"""How much ceremony a spec gets: what may be written and approved when, and what the model is told."""

import pytest

from codepilot import spec_profiles as profiles

ALL = {"requirements", "design", "tasks"}


@pytest.mark.parametrize("profile,phase,doc,ok", [
    ("full", "requirements", "requirements", True),
    ("full", "requirements", "design", False),
    ("full", "design", "tasks", False),
    ("full", "tasks", "design", True),
    ("full", "implement", "tasks", True),
    ("quick", "requirements", "requirements", True),
    ("quick", "requirements", "design", True),
    ("quick", "requirements", "tasks", True),
    ("quick", "implement", "tasks", True),
])
def test_what_may_be_written(profile, phase, doc, ok):
    assert profiles.may_write(profile, phase, doc) is ok


@pytest.mark.parametrize("profile,phase,target,docs,refused", [
    ("full", "requirements", "requirements", {"requirements"}, None),
    ("full", "requirements", "design", ALL, "Approve requirements first."),
    ("full", "design", "requirements", ALL, None),  # approving again after an edit
    ("quick", "requirements", "tasks", ALL, None),
    ("quick", "requirements", "tasks", {"requirements"},
     "Write the design and tasks first (or ask codepilot to finish the plan)."),
    ("quick", "requirements", "requirements", ALL, "A quick spec is approved as one plan."),
    ("quick", "implement", "tasks", ALL, None),
])
def test_what_may_be_approved(profile, phase, target, docs, refused):
    assert profiles.may_approve(profile, phase, target, docs) == refused


def test_a_missing_document_is_named():
    assert "design" in profiles.may_approve("full", "design", "design", {"requirements"})


def test_only_an_unapproved_spec_can_switch_to_full_review():
    assert profiles.can_switch_to_full("") and not profiles.can_switch_to_full("tasks")


@pytest.mark.parametrize("kind", ["feature", "bugfix"])
@pytest.mark.parametrize("phase", ["requirements", "design", "tasks"])
def test_full_documents_have_a_budget(kind, phase):
    text = profiles.instructions("full", kind, phase)
    assert "at most 5 acceptance criteria" in text and "150 lines" in text and "splitting" in text


def test_a_full_spec_is_told_its_phase_as_before():
    assert "Phase 2 of 3, DESIGN" in profiles.instructions("full", "feature", "design")
    assert "BUGFIX ANALYSIS" in profiles.instructions("full", "bugfix", "requirements")


@pytest.mark.parametrize("kind,word", [("feature", "requirements"), ("bugfix", "Current behaviour")])
def test_a_quick_spec_writes_all_three_within_its_budget(kind, word):
    text = profiles.instructions("quick", kind, "requirements")
    assert word in text and all(f"doc='{d}'" in text for d in ALL)
    assert "at most 3" in text and "4 criteria" in text and "40 lines" in text and "at most 6 tasks" in text
    assert "approve it in the Spec tab" in text


def test_implementing_is_the_same_for_both():
    assert profiles.instructions("quick", "feature", "implement") == profiles.instructions("full", "feature", "implement")


@pytest.mark.parametrize("text,expected", [
    ("quick add csv export", ("quick", "add csv export")),
    ("Quick   add csv", ("quick", "add csv")),
    ("add a quick filter", ("full", "add a quick filter")),
    ("quickly add csv", ("full", "quickly add csv")),
    ("quick", ("full", "quick")),
])
def test_asking_for_a_quick_spec(text, expected):
    assert profiles.requested(text) == expected
