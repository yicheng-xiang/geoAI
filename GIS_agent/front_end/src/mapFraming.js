export const HONG_KONG_BOUNDS = [[22.15, 113.83], [22.57, 114.45]];

export function framingOptions(width, height) {
  const compact = width < 600;
  return {
    paddingTopLeft: [compact ? 20 : 36, Math.min(96, height * 0.17)],
    paddingBottomRight: [compact ? 20 : 36, Math.min(52, height * 0.09)],
    maxZoom: 15,
    animate: false,
  };
}
