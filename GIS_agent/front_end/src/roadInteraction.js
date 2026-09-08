// A service-area MultiLineString is selected as one network. Popup lifecycle
// also clears selection when another feature or the map background is clicked.
export function roadInteractionStyle(base, selected = false, hovered = false) {
  if (selected) return { ...base, color: '#ea580c', weight: 3, opacity: 1, fill: false };
  if (hovered) return { ...base, color: '#0891b2', weight: 2.5, opacity: 1, fill: false };
  return { ...base };
}

export function bindRoadInteraction(leafletLayer, baseStyle) {
  let selected = false;
  let hovered = false;
  const update = () => leafletLayer.setStyle(roadInteractionStyle(baseStyle, selected, hovered));
  leafletLayer.on({
    mouseover: () => { hovered = true; update(); },
    mouseout: () => { hovered = false; update(); },
    popupopen: () => { selected = true; update(); },
    popupclose: () => { selected = false; hovered = false; update(); },
  });
}
