from tool_results import tool_error, tool_success


def add_scale_bar(state, length_km=10, position=(0.05, 0.05)):
    """Update browser scale-bar metadata; placement is controlled responsively by the client."""
    try:
        length_km = float(length_km)
    except (TypeError, ValueError):
        return tool_error("INVALID_SCALE_LENGTH", "Scale-bar length must be a number.")
    if length_km <= 0:
        return tool_error("INVALID_SCALE_LENGTH", "Scale-bar length must be greater than zero.")
    state.setdefault("web_map", {})["scale_bar_km"] = length_km
    return tool_success(f"Scale bar set to {length_km:g} km for the interactive map and PNG export.")


def add_title(state, text="Hong Kong Spatial Distribution Map", fontsize=15):
    """Update the canonical browser-map title."""
    title = str(text).strip()
    if not title:
        return tool_error("INVALID_MAP_TITLE", "Map title cannot be empty.")
    state.setdefault("web_map", {})["title"] = title
    state["web_map"]["title_fontsize"] = int(fontsize)
    return tool_success(f"Main title overwritten successfully to: '{title}'.")


def add_compass(state, x=0.92, y=0.84, scale=0.06):
    """Enable the responsive SVG north arrow in the browser presentation."""
    state.setdefault("web_map", {})["show_compass"] = True
    return tool_success("North arrow enabled for the interactive map and PNG export.")


def add_gridlines(state):
    """Retain the clean four-corner coordinate design without full graticule lines."""
    state.setdefault("web_map", {})["show_gridlines"] = False
    state["web_map"]["show_corner_coordinates"] = True
    return tool_success("Dynamic corner coordinates enabled; full graticule lines remain hidden.")
