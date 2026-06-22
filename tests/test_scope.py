from app.config import Settings
from app.scope import assess_scope, changed_line_count


def test_changed_line_count_counts_added_and_removed():
    old = "a\nb\nc\n"
    new = "a\nB\nc\nd\n"  # b->B (1 del + 1 add), +d (1 add) = 3
    assert changed_line_count(old, new) == 3


def test_create_counts_full_content():
    assert changed_line_count("", "x\ny\nz\n") == 3


def test_small_edit_to_large_file_stays_small():
    old = "\n".join(f"line {i}" for i in range(1000)) + "\n"
    new = old.replace("line 500", "line 500 patched")
    # одна правка в большом файле -> 2 строки диффа (del+add), не 1000
    assert changed_line_count(old, new) == 2


def test_within_budget_for_small_diff():
    s = Settings(max_diff_lines_auto=500, max_changed_files_medium=15)
    v = assess_scope({"app/f.py": ""}, {"app/f.py": "x = 1\n"}, [], settings=s)
    assert v.within_budget is True
    assert v.diff_lines == 1
    assert v.changed_files == 1
    assert v.reasons == []


def test_over_diff_budget_routes_to_human():
    s = Settings(max_diff_lines_auto=10, max_changed_files_medium=15)
    big = "\n".join(str(i) for i in range(50)) + "\n"
    v = assess_scope({}, {"app/f.py": big}, [], settings=s)
    assert v.within_budget is False
    assert v.diff_lines == 50
    assert any("diff" in r for r in v.reasons)


def test_over_file_budget_routes_to_human():
    s = Settings(max_diff_lines_auto=10_000, max_changed_files_medium=2)
    files = {f"app/f{i}.py": "x = 1\n" for i in range(3)}
    v = assess_scope({}, files, [], settings=s)
    assert v.within_budget is False
    assert any("changed files" in r for r in v.reasons)


def test_deletion_counts_removed_lines():
    s = Settings(max_diff_lines_auto=2, max_changed_files_medium=15)
    v = assess_scope({"app/old.py": "a\nb\nc\n"}, {}, ["app/old.py"], settings=s)
    assert v.diff_lines == 3
    assert v.within_budget is False
