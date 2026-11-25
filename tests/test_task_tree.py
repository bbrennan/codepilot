"""A spec's tasks as a tree: a task with sub-tasks is a heading, and its checkbox follows theirs."""

from codepilot import specs, task_tree

TREE = """- [ ] 1. Export
  - [x] 1.1 Writer
  - [ ] 1.2 Streaming
    - [ ] 1.2.1 Chunks
    - [-] 1.2.2 Back-pressure
- [ ] 2. Button
"""


def ids(tasks):
    return [t.id for t in tasks]


def test_leaves_are_the_work():
    tasks = specs.parse_tasks(TREE)
    assert ids(task_tree.leaves(tasks)) == ["1.1", "1.2.1", "1.2.2", "2"]
    assert ids(task_tree.open_under(tasks, "1")) == ["1.2.1", "1.2.2"]
    assert ids(task_tree.ancestors(tasks, "1.2.2")) == ["1.2", "1"]


def test_a_heading_follows_its_sub_tasks():
    tasks = specs.parse_tasks(TREE)
    assert task_tree.rolled_up(tasks, "1.2") == "in_progress"  # one started
    assert task_tree.rolled_up(specs.parse_tasks("- [ ] 1. A\n  - [ ] 1.1 B\n"), "1") == "todo"
    assert task_tree.rolled_up(specs.parse_tasks("- [ ] 1. A\n  - [x] 1.1 B\n"), "1") == "done"


def test_a_heading_with_open_work_cant_be_done():
    tasks = specs.parse_tasks(TREE)
    why = task_tree.refuse_done(tasks, "1")
    assert "1.2.1 (Chunks)" in why and "1.2.2 (Back-pressure)" in why and "1.1" not in why
    assert task_tree.refuse_done(tasks, "1.1") is None and task_tree.refuse_done(tasks, "2") is None


def test_the_note_says_where_the_parent_stands():
    tasks = specs.parse_tasks(TREE)
    assert task_tree.note(tasks, "1.1") == \
        " Task 1 (Export) is todo; still open under it: 1.2.1 (Chunks), 1.2.2 (Back-pressure)."
    assert task_tree.note(tasks, "2") == ""
    done = specs.parse_tasks("- [x] 1. A\n  - [x] 1.1 B\n")
    assert task_tree.note(done, "1.1") == " Task 1 (A) is done too: all its sub-tasks are."


def test_ids_are_normalised():
    assert [task_tree.normalise(x) for x in ("1.1", "1.1.", "Task 1.1", "task 1.1:", "1.1 Write it", " 2 ")] == \
        ["1.1", "1.1", "1.1", "1.1", "1.1", "2"]
    assert task_tree.normalise("Writer") == "Writer"  # not a number: left for the caller to refuse


def test_duplicates_are_found():
    tasks = specs.parse_tasks("- [ ] 1. A\n- [ ] 1. B\n- [ ] 2. C\n")
    assert [t.title for t in task_tree.duplicates(tasks, "1")] == ["A", "B"] and task_tree.duplicates(tasks, "2") == []
