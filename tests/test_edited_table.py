from aula_f108.edited_table import EditedTable


def test_starts_with_the_table_and_no_edits():
    table = EditedTable(["a", "b", "c"])
    assert [table.value(index) for index in range(3)] == ["a", "b", "c"]
    assert table.edited() == frozenset()
    assert table.changes() == {}


def test_edit_changes_the_value_and_is_a_change():
    table = EditedTable(["a", "b", "c"])
    table.edit(1, "x")
    assert table.value(1) == "x"
    assert table.edited() == frozenset({1})
    assert table.changes() == {1: "x"}


def test_edit_back_to_the_table_value_is_an_edit():
    table = EditedTable(["a", "b", "c"])
    table.edit(1, "x")
    table.edit(1, "b")
    assert table.edited() == frozenset({1})
    assert table.changes() == {1: "b"}


def test_edit_equal_to_the_table_is_an_edit():
    table = EditedTable(["a", "b", "c"])
    table.edit(2, "c")
    assert table.changes() == {2: "c"}


def test_new_table_keeps_the_edits_on_top():
    table = EditedTable(["a", "b", "c"])
    table.edit(0, "x")
    table.set_base(["d", "e", "f"])
    assert [table.value(index) for index in range(3)] == ["x", "e", "f"]
    assert table.changes() == {0: "x"}


def test_new_table_that_holds_an_edit_keeps_it():
    table = EditedTable(["a", "b", "c"])
    table.edit(0, "x")
    table.edit(1, "y")
    table.set_base(["x", "b", "c"])
    assert table.changes() == {0: "x", 1: "y"}


def test_new_table_does_not_clear_an_edit_back_to_the_old_value():
    table = EditedTable(["a", "b", "c"])
    table.edit(1, "x")
    table.edit(1, "b")
    table.set_base(["a", "b", "c"])
    assert table.changes() == {1: "b"}


def test_discard_drops_every_edit():
    table = EditedTable(["a", "b", "c"])
    table.edit(0, "x")
    table.discard()
    assert table.value(0) == "a"
    assert table.edited() == frozenset()


def test_every_edit_gets_a_higher_sequence_number():
    table = EditedTable(["a", "b", "c"])
    assert table.last_edit() == 0
    table.edit(0, "x")
    first = table.last_edit()
    table.edit(1, "y")
    second = table.last_edit()
    table.edit(0, "x")  # a repaint of the same entry with the same value is a newer edit
    assert 0 < first < second < table.last_edit()


def test_written_table_clears_the_applied_edits_it_holds():
    table = EditedTable(["a", "b", "c"])
    table.edit(0, "x")
    table.edit(1, "y")
    table.set_written(["x", "b", "c"], table.last_edit())
    assert table.changes() == {1: "y"}
    assert table.value(0) == "x"


def test_written_table_keeps_an_applied_edit_that_differs_from_the_written_value():
    table = EditedTable(["a", "b", "c"])
    table.edit(1, "x")
    applied = table.last_edit()
    table.edit(1, "b")  # repainted to the old value while the write of "x" runs
    table.set_written(["a", "x", "c"], applied)
    assert table.changes() == {1: "b"}
    assert table.value(1) == "b"


def test_written_table_keeps_an_edit_made_after_the_apply_even_when_it_equals_the_written_value():
    table = EditedTable(["a", "b", "c"])
    table.edit(1, "x")
    applied = table.last_edit()
    table.edit(1, "x")
    table.set_written(["a", "x", "c"], applied)
    assert table.changes() == {1: "x"}


def test_written_table_replaces_the_base_and_clears_nothing_for_an_apply_without_edits():
    table = EditedTable(["a", "b", "c"])
    table.edit(1, "b")
    table.set_written(["a", "b", "z"], 0)
    assert table.changes() == {1: "b"}
    assert table.value(2) == "z"
