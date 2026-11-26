import os

# Qt widgets in tests run on the "minimal" platform, so the suite needs no display. The "offscreen"
# platform is not used: on this system it picks the Noto Color Emoji font as the default font and
# crashes in the text layout of word-wrapped labels.
os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

# The hardware tests write to the real keyboard; they are collected only on request.
collect_ignore_glob = [] if os.environ.get("AULA_HARDWARE") == "1" else ["hardware/*"]
