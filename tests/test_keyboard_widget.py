import pytest
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPalette, QPolygonF

from aula_f108.layout import load_layout
from aula_f108.ui import keyboard_widget
from aula_f108.ui.keyboard_widget import KeyboardWidget, label_colour
from mouse import move, press, release

ESC, F1, PLUS = 0, 1, 110
UP = 90
GAP = QPointF(80, 29)  # between Esc (x 4..54) and F1 (x 112..162) at scale 1


@pytest.fixture
def widget(qtbot):
    widget = KeyboardWidget(load_layout())
    qtbot.addWidget(widget)
    widget.resize(1205, 333)  # the layout is 1197 × 325 units, plus a margin of 4: one pixel per unit
    widget.touches = []
    widget.touched.connect(widget.touches.append)
    return widget


def centre(widget, index):
    return widget.key_rect(index).center()


def rgb_at(widget, point):
    return QColor(widget.grab().toImage().pixel(int(point.x()), int(point.y()))).getRgb()[:3]


def fill_point(widget, index):
    rect = widget.key_rect(index)
    return QPointF(rect.left() + rect.width() * 0.15, rect.bottom() - rect.height() * 0.15)


def test_keys_are_placed_from_the_layout(widget):
    assert widget.key_rect(ESC) == QRectF(4, 4, 50, 50)
    assert widget.key_rect(F1) == QRectF(112, 4, 50, 50)


def test_keys_scale_with_the_widget(widget):
    widget.resize(2402, 658)
    assert widget.key_rect(ESC) == QRectF(4, 4, 100, 100)


def test_keys_are_centred_in_a_wider_widget(widget):
    widget.resize(1405, 333)
    assert widget.key_rect(ESC) == QRectF(104, 4, 50, 50)


def test_keys_are_centred_in_a_taller_widget(widget):
    widget.resize(1205, 433)
    assert widget.key_rect(ESC) == QRectF(4, 54, 50, 50)


def test_item_at_finds_the_key_under_a_point(widget):
    assert widget.item_at(centre(widget, ESC)) == ESC
    assert widget.item_at(centre(widget, PLUS)) == PLUS
    assert widget.item_at(GAP) is None


def test_press_touches_the_key(widget):
    press(widget, centre(widget, ESC))
    assert widget.touches == [ESC]


def test_drag_touches_each_new_key_once(widget):
    press(widget, centre(widget, ESC))
    move(widget, centre(widget, ESC) + QPointF(5, 5))
    move(widget, GAP)
    move(widget, centre(widget, F1))
    assert widget.touches == [ESC, F1]


def test_release_ends_the_drag(widget):
    press(widget, centre(widget, ESC))
    release(widget, centre(widget, ESC))
    move(widget, centre(widget, F1))
    assert widget.touches == [ESC]


def test_release_of_another_button_keeps_the_drag(widget):
    press(widget, centre(widget, ESC))
    release(widget, centre(widget, ESC), Qt.MouseButton.RightButton)
    move(widget, centre(widget, F1))
    assert widget.touches == [ESC, F1]


def test_right_button_paints_nothing(widget):
    press(widget, centre(widget, ESC), Qt.MouseButton.RightButton)
    move(widget, centre(widget, F1))
    assert widget.touches == []


def test_move_without_a_press_paints_nothing(widget):
    move(widget, centre(widget, F1))
    assert widget.touches == []


def test_press_in_a_gap_paints_nothing(widget):
    press(widget, GAP)
    assert widget.touches == []


def test_keys_show_their_colour_and_keys_without_one_the_button_colour(widget):
    widget.set_colours({ESC: (255, 0, 0)})
    assert widget.colour(ESC) == (255, 0, 0)
    assert widget.colour(F1) is None
    assert rgb_at(widget, fill_point(widget, ESC)) == (255, 0, 0)
    assert rgb_at(widget, fill_point(widget, F1)) == widget.palette().color(QPalette.ColorRole.Button).getRgb()[:3]


def test_marked_keys_show_a_dot(widget):
    widget.set_colours({ESC: (0, 0, 0), F1: (0, 0, 0)})
    widget.set_marked({ESC})
    assert widget.is_marked(ESC)
    assert not widget.is_marked(F1)
    highlight = widget.palette().color(QPalette.ColorRole.Highlight).getRgb()[:3]
    assert rgb_at(widget, widget.mark_rect(ESC).center()) == highlight
    assert rgb_at(widget, widget.mark_rect(F1).center()) == (0, 0, 0)


def test_keys_show_their_labels(widget, monkeypatch):
    """The minimal platform has no fonts, so the pixels hold no text: record what the painter is asked to draw."""
    drawn = []

    class RecordingPainter(QPainter):
        def drawText(self, rect, flags, text):
            drawn.append((rect, text))
            super().drawText(rect, flags, text)

    monkeypatch.setattr(keyboard_widget, "QPainter", RecordingPainter)
    widget.grab()
    assert len(drawn) == 104  # the four arrow keys are drawn as shapes
    assert (widget.key_rect(ESC), "ESC") in drawn
    assert (widget.key_rect(F1), "F1") in drawn


def test_label_colour_contrasts_with_the_key():
    assert label_colour(QColor(255, 255, 255)) == QColor(Qt.GlobalColor.black)
    assert label_colour(QColor(0, 0, 0)) == QColor(Qt.GlobalColor.white)


def test_arrow_keys_are_painted_as_triangles_and_not_as_text(widget, monkeypatch):
    """Drawing an arrow glyph makes Qt 5 look up a fallback font, which can crash in fontconfig."""
    texts, polygons = [], []

    class RecordingPainter(QPainter):
        def drawText(self, rect, flags, text):
            texts.append(text)
            super().drawText(rect, flags, text)

        def drawPolygon(self, polygon, *args):
            polygons.append(QPolygonF(polygon))
            super().drawPolygon(polygon, *args)

    monkeypatch.setattr(keyboard_widget, "QPainter", RecordingPainter)
    widget.grab()
    assert len(texts) == 104
    assert not any(char in text for text in texts for char in "←↑→↓")
    assert len(polygons) == 4
    for polygon in polygons:
        assert polygon.size() == 3
    key_rect = widget.key_rect(UP)
    up = next(polygon for polygon in polygons if key_rect.contains(polygon.boundingRect()))
    bounding = up.boundingRect()
    assert bounding.center().x() == pytest.approx(key_rect.center().x())
    assert bounding.center().y() == pytest.approx(key_rect.center().y())
    assert min(up, key=lambda point: point.y()).x() == pytest.approx(key_rect.center().x())


def test_given_labels_replace_the_key_labels_and_arrows_in_a_smaller_font(widget, monkeypatch):
    drawn, polygons = [], []

    class RecordingPainter(QPainter):
        def drawText(self, rect, flags, text):
            drawn.append((rect, text, self.font().pixelSize()))
            super().drawText(rect, flags, text)

        def drawPolygon(self, polygon, *args):
            polygons.append(QPolygonF(polygon))
            super().drawPolygon(polygon, *args)

    monkeypatch.setattr(keyboard_widget, "QPainter", RecordingPainter)
    widget.set_labels({ESC: "Factory Reset", UP: "A"})
    assert widget.label(ESC) == "Factory Reset"
    assert widget.label(F1) is None
    widget.grab()
    assert (widget.key_rect(ESC), "Factory Reset", 9) in drawn
    assert (widget.key_rect(UP), "A", 9) in drawn
    assert (widget.key_rect(F1), "F1", 13) in drawn
    assert len(drawn) == 105  # the 104 labels, with Esc's replaced, and the up arrow's label
    assert len(polygons) == 3


def test_selected_key_is_outlined(widget):
    highlight = widget.palette().color(QPalette.ColorRole.Highlight).getRgb()[:3]
    button = widget.palette().color(QPalette.ColorRole.Button).getRgb()[:3]

    def edge(index):
        rect = widget.key_rect(index)
        return QPointF(rect.left() + 2, rect.center().y())

    assert widget.selected() is None
    assert rgb_at(widget, edge(ESC)) == button
    widget.set_selected(ESC)
    assert widget.selected() == ESC
    assert rgb_at(widget, edge(ESC)) == highlight
    assert rgb_at(widget, edge(F1)) == button
    widget.set_selected(None)
    assert rgb_at(widget, edge(ESC)) == button
