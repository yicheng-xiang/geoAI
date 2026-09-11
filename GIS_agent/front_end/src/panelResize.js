export function panelHeight(value, viewportHeight) {
  return Math.max(240, Math.min(Math.max(240, Math.min(650, viewportHeight * .65)), value));
}

export function draggedPanelHeight(start, clientY, viewportHeight) {
  return panelHeight(start.height + clientY - start.y, viewportHeight);
}
