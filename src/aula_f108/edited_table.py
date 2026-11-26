"""Unapplied edits of a table read from the keyboard, as kept by the pages with an "Apply" button."""


class EditedTable:
    """Entries the user changed, kept over the table last read from or written to the keyboard.

    Every edit stays, also when it equals the entry underneath, because a write that is still running may change that
    entry. Every edit gets a sequence number that rises with each `edit` call, also for an entry that is edited again.
    A table read from the keyboard keeps the edits on top. The table that the keyboard returns after a write clears
    the edits that were sent with that write and whose value it holds. `discard` drops them all.
    """

    def __init__(self, table):
        self._base = tuple(table)
        self._edits = {}  # index -> (sequence number, value)
        self._count = 0

    def set_base(self, table) -> None:
        self._base = tuple(table)

    def set_written(self, table, applied: int) -> None:
        """Replace the table underneath with a written one and clear the edits up to the sequence number `applied`
        whose value it holds. Later edits stay."""
        self.set_base(table)
        self._edits = {
            index: (seq, value)
            for index, (seq, value) in self._edits.items()
            if seq > applied or value != self._base[index]
        }

    def edit(self, index: int, value) -> None:
        self._count += 1
        self._edits[index] = (self._count, value)

    def last_edit(self) -> int:
        """The highest sequence number of the edits, 0 without edits."""
        return max((seq for seq, _value in self._edits.values()), default=0)

    def value(self, index: int):
        return self._edits[index][1] if index in self._edits else self._base[index]

    def edited(self) -> frozenset:
        return frozenset(self._edits)

    def changes(self) -> dict:
        return {index: value for index, (_seq, value) in self._edits.items()}

    def discard(self) -> None:
        self._edits.clear()
