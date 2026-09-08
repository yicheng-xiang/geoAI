// Export the actual laid-out HTML/SVG overlays, not a second canvas design.
// All styles (including generated scale-bar ticks) are frozen before decoding.
function copyStyle(source, target, pseudo) {
  const style = getComputedStyle(source, pseudo);
  for (const key of style) target.style.setProperty(key, style.getPropertyValue(key));
  target.style.setProperty('animation', 'none');
  target.style.setProperty('transition', 'none');
  return style;
}

function styledClone(source) {
  const clone = source.cloneNode(false);
  copyStyle(source, clone);
  clone.removeAttribute('id');
  // Hyperlinks are rendered as text; the snapshot needs no external resources.
  if (clone.tagName === 'A') clone.removeAttribute('href');
  for (const node of source.childNodes) {
    clone.append(node.nodeType === Node.ELEMENT_NODE ? styledClone(node) : node.cloneNode(true));
  }
  if (source.namespaceURI === 'http://www.w3.org/1999/xhtml') {
    for (const pseudo of ['::before', '::after']) {
      const style = getComputedStyle(source, pseudo);
      if (!style.content || ['none', 'normal'].includes(style.content)) continue;
      const element = document.createElement('span');
      copyStyle(source, element, pseudo);
      element.textContent = style.content.replace(/^['"]|['"]$/g, '');
      if (pseudo === '::before') clone.prepend(element); else clone.append(element);
    }
  }
  return clone;
}

export async function captureMapOverlays(root, mapRect) {
  await document.fonts.ready;
  const host = document.createElement('div');
  host.setAttribute('xmlns', 'http://www.w3.org/1999/xhtml');
  host.style.cssText = `position:relative;width:${mapRect.width}px;height:${mapRect.height}px;overflow:hidden;`;
  const selectors = [
    '.district-map-label', '.geoai-point-marker', '.map-coordinate',
    '.map-compass', '.map-title-card', '.map-reference-card', '.map-legend',
  ];
  for (const selector of selectors) {
    for (const element of root.querySelectorAll(selector)) {
      const rect = element.getBoundingClientRect();
      if (!rect.width || !rect.height || getComputedStyle(element).visibility === 'hidden') continue;
      const clone = styledClone(element);
      Object.assign(clone.style, {
        position: 'absolute', left: `${rect.left - mapRect.left}px`, top: `${rect.top - mapRect.top}px`,
        right: 'auto', bottom: 'auto', margin: '0', transform: 'none', boxSizing: 'border-box',
        width: `${rect.width}px`, height: `${rect.height}px`, maxWidth: 'none', maxHeight: 'none',
      });
      host.append(clone);
    }
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${mapRect.width * 2}" height="${mapRect.height * 2}" viewBox="0 0 ${mapRect.width} ${mapRect.height}"><foreignObject width="100%" height="100%">${new XMLSerializer().serializeToString(host)}</foreignObject></svg>`;
  const image = new Image();
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  await image.decode();
  return image;
}
