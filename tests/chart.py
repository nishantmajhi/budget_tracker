"""Render the tracker's plotext charts into a grid a test can read.

plotext draws both series with the same block characters and tells them apart
only by colour, so the rendered string is decoded cell by cell: a bar cell in
green becomes `G`, one in red `R`, and everything else is left as it was.
"""

import re

_CELL = re.compile(r"((?:\x1b\[[0-9;]*m)*)([^\x1b])")
_CODE = re.compile(r"\x1b\[([0-9;]*)m")
_BAR = set("█▄▀▌▐")
_NAMES = {"1": "R", "2": "G"}


def decode(rendered):
    """Turn plotext's ANSI output into lines of plain characters and G/R."""
    lines = []
    for line in rendered.splitlines():
        out, fg = [], None
        for codes, ch in _CELL.findall(line):
            for code in _CODE.findall(codes):
                if code.startswith("38;5;"):
                    fg = code[5:]
                elif code == "0":
                    fg = None
            out.append(_NAMES.get(fg, "?") if ch in _BAR else ch)
        lines.append("".join(out))
    return lines


def capture(session, function_name):
    """Call a charting feature and return each chart it showed, decoded."""
    charts = []
    plt = session.m.plt

    def show():
        plt.plotsize(60, 16)
        charts.append(decode(plt.build()))

    original_show = plt.show
    plt.show = show
    try:
        session.call(function_name)
    finally:
        plt.show = original_show
    return charts


def runs(line):
    """The colour runs along one row, e.g. 'GRGR' for two grouped months."""
    return "".join(run[0] for run in re.findall(r"G+|R+", line))


def bottom_row(chart):
    """The lowest row of bars, just above the x axis.

    Only what is inside the plot frame counts: the axis label "Amount (GBP)"
    below it has a G of its own."""
    inside = [area for area in map(_plot_area, chart) if area is not None]
    bar_rows = [area for area in inside if "G" in area or "R" in area]
    return bar_rows[-1]


def _plot_area(line):
    """The part of a chart line between the left axis and the right frame."""
    starts = [i for i in (line.find("┤"), line.find("│")) if i >= 0]
    end = line.rfind("│")
    if not starts or end <= min(starts):
        return None
    return line[min(starts) + 1:end]
