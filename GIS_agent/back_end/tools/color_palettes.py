import math
import re


PALETTES = {
    "Blues": ["#f7fbff", "#deebf7", "#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#08519c", "#08306b"],
    "Greens": ["#f7fcf5", "#e5f5e0", "#c7e9c0", "#a1d99b", "#74c476", "#41ab5d", "#238b45", "#006d2c", "#00441b"],
    "Purples": ["#fcfbfd", "#efedf5", "#dadaeb", "#bcbddc", "#9e9ac8", "#807dba", "#6a51a3", "#54278f", "#3f007d"],
    "Reds": ["#fff5f0", "#fee0d2", "#fcbba1", "#fc9272", "#fb6a4a", "#ef3b2c", "#cb181d", "#a50f15", "#67000d"],
    "Oranges": ["#fff5eb", "#fee6ce", "#fdd0a2", "#fdae6b", "#fd8d3c", "#f16913", "#d94801", "#a63603", "#7f2704"],
    "YlOrRd": ["#ffffcc", "#ffeda0", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#bd0026", "#800026"],
    "viridis": ["#440154", "#482878", "#3e4989", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725"],
    "Set1": ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#ffff33", "#a65628", "#f781bf", "#999999"],
    "tab10": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"],
    "tab20": ["#1f77b4", "#aec7e8", "#ff7f0e", "#ffbb78", "#2ca02c", "#98df8a", "#d62728", "#ff9896", "#9467bd", "#c5b0d5", "#8c564b", "#c49c94", "#e377c2", "#f7b6d2", "#7f7f7f", "#c7c7c7", "#bcbd22", "#dbdb8d", "#17becf", "#9edae5"],
}

SEQUENTIAL_PALETTES = {"Blues", "Greens", "Purples", "Reds", "Oranges", "YlOrRd", "viridis"}
NAMED_COLORS = {
    "black": "#000000", "red": "#ff0000", "blue": "#0000ff", "green": "#008000",
    "yellow": "#ffff00", "orange": "#ffa500", "purple": "#800080", "white": "#ffffff",
}
HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def literal_color(value):
    text = str(value or "").strip()
    if HEX_COLOR.fullmatch(text):
        if len(text) == 4:
            text = "#" + "".join(character * 2 for character in text[1:])
        return text.lower()
    return NAMED_COLORS.get(text.lower())


def _rgb(color):
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))


def _interpolate(stops, position):
    scaled = max(0.0, min(1.0, position)) * (len(stops) - 1)
    lower = int(math.floor(scaled))
    upper = min(len(stops) - 1, lower + 1)
    fraction = scaled - lower
    start = _rgb(stops[lower])
    end = _rgb(stops[upper])
    values = [round(first + ((second - first) * fraction)) for first, second in zip(start, end)]
    return "#" + "".join(f"{value:02x}" for value in values)


def sample_palette(name, count, start=0.25, end=0.85):
    """Return deterministic CSS hex colors without requiring a plotting library."""
    count = max(0, int(count))
    if count == 0:
        return []
    canonical = next((key for key in PALETTES if key.lower() == str(name).lower()), None)
    stops = PALETTES.get(canonical or "tab10")
    if canonical not in SEQUENTIAL_PALETTES:
        return [stops[index % len(stops)] for index in range(count)]
    if count == 1:
        return [_interpolate(stops, 0.7)]
    return [_interpolate(stops, start + ((end - start) * index / (count - 1))) for index in range(count)]
