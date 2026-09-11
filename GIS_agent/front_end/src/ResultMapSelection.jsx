import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';

// A separate, non-interactive pane keeps selection out of PNG export and leaves
// original hover styles untouched. Feature identity never depends on a label.
export default function ResultMapSelection({ selection, registry, revision, createPointIcon }) {
  const map = useMap();
  useEffect(() => {
    const entry = selection && registry.current.get(selection.featureId);
    if (!entry) return undefined;
    const pane = map.getPane('result-selection') || map.createPane('result-selection');
    pane.style.zIndex = '650'; pane.style.pointerEvents = 'none';
    const style = { pane: 'result-selection', interactive: false, color: '#0284c7', weight: 1.5, fillOpacity: 0, opacity: .9 };
    const highlight = L.geoJSON(entry.feature, { pane: 'result-selection', interactive: false, style,
      pointToLayer: (_, latlng) => L.marker(latlng, {
        pane: 'result-selection', interactive: false, keyboard: false,
        icon: createPointIcon('location', { fillColor: '#329eb5', color: '#ffffff' }),
      }) }).addTo(map);
    if (selection.focus) {
      const point = entry.layer.getLatLng?.();
      if (point) { if (!map.getBounds().contains(point)) map.panTo(point); }
      else if (entry.layer.getBounds) map.fitBounds(entry.layer.getBounds(), { padding: [45, 45], maxZoom: 15 });
    }
    // Use the existing popup content/style, anchored above the same location
    // template used by analysis centers, instead of stacking a second design.
    const point = entry.layer.getLatLng?.();
    const popup = entry.layer.getPopup?.();
    if (point && popup) {
      entry.layer.closePopup?.();
      highlight.bindPopup(popup.getContent(), { ...popup.options, offset: [0, -28] }).openPopup(point);
    } else entry.layer.openPopup?.();
    return () => { map.removeLayer(highlight); entry.layer.closePopup?.(); };
  }, [selection, map, registry, revision, createPointIcon]);
  return null;
}
