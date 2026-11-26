"""The keyboard picture: the 108 keys drawn from the layout coordinates, with labels, colours and edit marks."""
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPalette, QPen, QPolygonF
from PyQt5.QtWidgets import QSizePolicy

from aula_f108.layout import Arrow, bounds
from aula_f108.ui.widgets import TouchArea, is_light

MARGIN = 4        # pixels around the keys
LABEL_SIZE = 13   # label height in layout units
ACTION_LABEL_SIZE = 9  # height of a label given with set_labels: action names are longer than key names
SELECTION_WIDTH = 4    # width of the outline of the selected key, in layout units
CORNER = 4        # corner radius in layout units
MARK_SIZE = 0.24  # diameter of the mark of an edited key, as a part of the key height
ARROW_SIZE = 0.4  # side of the square around an arrow, as a part of the shorter key side
# The corners of the arrow in a unit square around the origin.
ARROW_CORNERS = {
    Arrow.UP: ((0, -0.5), (0.5, 0.5), (-0.5, 0.5)),
    Arrow.DOWN: ((0, 0.5), (-0.5, -0.5), (0.5, -0.5)),
    Arrow.LEFT: ((-0.5, 0), (0.5, -0.5), (0.5, 0.5)),
    Arrow.RIGHT: ((0.5, 0), (-0.5, 0.5), (-0.5, -0.5)),
}


def label_colour(fill: QColor) -> QColor:
    light = is_light((fill.red(), fill.green(), fill.blue()))
    return QColor(Qt.GlobalColor.black if light else Qt.GlobalColor.white)


class KeyboardWidget(TouchArea):
    """Scales with the widget. `touched` carries the key index under the pressed left button."""

    def __init__(self, keys):
        super().__init__()
        self.keys = tuple(keys)
        self._by_index = {key.index: key for key in self.keys}
        self._left, self._top, self._right, self._bottom = bounds(self.keys)
        self._colours = {}
        self._marked = frozenset()
        self._labels = {}
        self._selected = None
        self.setMinimumSize(480, 140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_colours(self, colours: dict) -> None:
        """Colours by key index. A key without a colour shows the palette's button colour."""
        self._colours = dict(colours)
        self.update()

    def set_marked(self, indexes) -> None:
        self._marked = frozenset(indexes)
        self.update()

    def set_labels(self, labels: dict) -> None:
        """Labels by key index that replace the key's own label or arrow, drawn smaller."""
        self._labels = dict(labels)
        self.update()

    def set_selected(self, index: int | None) -> None:
        """Outline the key with this index; None outlines no key."""
        self._selected = index
        self.update()

    def colour(self, index: int):
        return self._colours.get(index)

    def label(self, index: int) -> str | None:
        """The label given with set_labels, None for a key that shows its own label."""
        return self._labels.get(index)

    def selected(self) -> int | None:
        return self._selected

    def is_marked(self, index: int) -> bool:
        return index in self._marked

    def key_rect(self, index: int) -> QRectF:
        key = self._by_index[index]
        scale, left, top = self._transform()
        return QRectF(left + (key.x - self._left) * scale, top + (key.y - self._top) * scale,
                      key.w * scale, key.h * scale)

    def mark_rect(self, index: int) -> QRectF:
        rect = self.key_rect(index)
        size = rect.height() * MARK_SIZE
        return QRectF(rect.right() - size * 1.5, rect.top() + size * 0.5, size, size)

    def arrow_polygon(self, index: int) -> QPolygonF:
        rect = self.key_rect(index)
        size = min(rect.width(), rect.height()) * ARROW_SIZE
        centre = rect.center()
        return QPolygonF([QPointF(centre.x() + x * size, centre.y() + y * size)
                          for x, y in ARROW_CORNERS[self._by_index[index].arrow]])

    def item_at(self, point) -> int | None:
        for key in self.keys:
            if self.key_rect(key.index).contains(QPointF(point)):
                return key.index
        return None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale, _left, _top = self._transform()
        font = QFont(self.font())
        font.setPixelSize(round(LABEL_SIZE * scale))
        action_font = QFont(self.font())
        action_font.setPixelSize(round(ACTION_LABEL_SIZE * scale))
        palette = self.palette()
        for key in self.keys:
            rect = self.key_rect(key.index)
            colour = self._colours.get(key.index)
            fill = palette.color(QPalette.ColorRole.Button) if colour is None else QColor(*colour)
            painter.setPen(palette.color(QPalette.ColorRole.Mid))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, CORNER * scale, CORNER * scale)
            painter.setPen(label_colour(fill))
            flags = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap)
            if key.index in self._labels:
                painter.setFont(action_font)
                painter.drawText(rect, flags, self._labels[key.index])
            elif key.arrow is None:
                painter.setFont(font)
                painter.drawText(rect, flags, key.label)
            else:
                # Qt 5 can crash in fontconfig while looking up a fallback font for a glyph the UI font lacks.
                # So the key labels hold only ASCII, and the arrows are drawn as shapes.
                painter.setBrush(label_colour(fill))
                painter.drawPolygon(self.arrow_polygon(key.index))
            if key.index in self._marked:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(palette.color(QPalette.ColorRole.Highlight))
                painter.drawEllipse(self.mark_rect(key.index))
            if key.index == self._selected:
                painter.setPen(QPen(palette.color(QPalette.ColorRole.Highlight), SELECTION_WIDTH * scale))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                inset = SELECTION_WIDTH * scale / 2
                painter.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset), CORNER * scale, CORNER * scale)
        painter.end()

    def _transform(self) -> tuple[float, float, float]:
        """Scale and the top left corner of the layout in widget pixels, keeping the aspect ratio."""
        width, height = self._right - self._left, self._bottom - self._top
        scale = min((self.width() - 2 * MARGIN) / width, (self.height() - 2 * MARGIN) / height)
        return scale, (self.width() - width * scale) / 2, (self.height() - height * scale) / 2
