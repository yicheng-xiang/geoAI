// Keep association tied to the mounted Leaflet instance, including StrictMode
// re-adds. An older instance must never unregister its replacement.
export function registerResultFeature(registry, feature, layer) {
  const id = feature.properties?._result_feature_id;
  if (!id) return;
  const register = () => registry.current.set(id, { feature, layer });
  register();
  layer.on('add', register);
  layer.on('remove', () => {
    if (registry.current.get(id)?.layer === layer) registry.current.delete(id);
  });
}
