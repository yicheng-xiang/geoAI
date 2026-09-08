import { useEffect, useState } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { SIMPLE_BASEMAP_URL, simplifyBasemap } from './basemapStyle.js';
import 'maplibre-gl/dist/maplibre-gl.css';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

export default function Basemap({ onReady }) {
  const map = useMap();
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let disposed = false;
    let layer;
    let notice;
    let fallback = false;
    const streets = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      crossOrigin: 'anonymous', maxZoom: 19,
    });
    map.getContainer().dataset.basemapKind = 'loading';
    onReady({ kind: 'loading' });
    const showNotice = (message, offerFallback = false) => {
      notice?.remove();
      notice = L.control({ position: 'bottomleft' });
      notice.onAdd = () => {
        const element = L.DomUtil.create('div', 'basemap-notice');
        element.setAttribute('role', 'status');
        element.textContent = message;
        L.DomEvent.disableClickPropagation(element);
        if (offerFallback) {
          const retry = L.DomUtil.create('button', '', element);
          retry.type = 'button';
          retry.textContent = 'Retry simplified basemap';
          retry.onclick = () => setAttempt((value) => value + 1);
          const button = L.DomUtil.create('button', '', element);
          button.type = 'button';
          button.textContent = 'Use detailed OSM basemap';
          button.onclick = () => {
            streets.addTo(map);
            map.getContainer().dataset.basemapKind = 'raster';
            onReady({ kind: 'raster' });
            showNotice('Detailed OSM basemap selected.');
          };
        }
        return element;
      };
      notice.addTo(map);
    };
    showNotice('Loading simplified basemap...');
    const controller = new AbortController();
    const showStreetFallback = (reason = 'The vector basemap did not load within 45 seconds.') => {
      if (disposed || fallback) return;
      fallback = true;
      controller.abort();
      if (layer) map.removeLayer(layer);
      layer = null;
      map.getContainer().dataset.basemapKind = 'error';
      map.getContainer().dataset.basemapError = reason;
      onReady({ kind: 'error' });
      showNotice('Simplified basemap unavailable. Retry, or explicitly choose the detailed basemap.', true);
    };
    const timeout = window.setTimeout(showStreetFallback, 45000);
    const resourceUrl = (url) => import.meta.env.DEV && url.startsWith('https://tiles.openfreemap.org/')
      ? url.replace('https://tiles.openfreemap.org/', `${window.location.origin}/basemap/`) : url;
    const start = async () => {
      try {
        const [module, response, maplibre] = await Promise.all([
          import('@maplibre/maplibre-gl-leaflet'),
          fetch(resourceUrl(SIMPLE_BASEMAP_URL), { signal: controller.signal }),
          import('maplibre-gl'),
        ]);
        if (!response.ok) throw new Error('Basemap style could not be loaded.');
        const style = simplifyBasemap(await response.json());
        if (disposed || fallback) return;
        // Vite moves dependency modules; bundle the worker explicitly so its
        // relative shared-module imports also resolve in development/builds.
        maplibre.setWorkerUrl(workerUrl);
        layer = module.maplibreGL({
          style, interactive: false, attributionControl: false, padding: 0,
          transformRequest: (url) => ({ url: resourceUrl(url) }),
          canvasContextAttributes: { preserveDrawingBuffer: true },
        }).addTo(map);
        const gl = layer.getMaplibreMap();
        layer.getContainer().style.opacity = '0';
        // Do not silently display/export a partially missing vector basemap.
        gl.on('error', (event) => {
          const message = event.error?.message || 'Basemap resource failed.';
          map.getContainer().dataset.basemapError = message;
          requestAnimationFrame(() => showStreetFallback(message));
        });
        const capture = async () => {
          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          return new Promise((resolve, reject) => {
            const started = Date.now();
            const check = () => {
              if (disposed || fallback) return reject(new Error('Basemap changed. Please export again.'));
              if (gl.loaded() && !gl.isMoving()) return resolve(gl.getCanvas());
              if (Date.now() - started > 8000) return reject(new Error('Basemap is still loading. Wait a moment and export again.'));
              window.setTimeout(check, 100);
            };
            check();
          });
        };
        gl.on('load', () => {
          if (disposed || fallback) return;
          window.clearTimeout(timeout);
          if (!gl.queryRenderedFeatures().length) {
            showStreetFallback('No basemap features were received.');
            return;
          }
          map.removeLayer(streets);
          notice?.remove();
          layer.getContainer().style.opacity = '1';
          map.getContainer().dataset.basemapKind = 'vector';
          onReady({ kind: 'vector', capture });
        });
      } catch (error) {
        showStreetFallback(error.message);
      }
    };
    start();
    return () => {
      disposed = true;
      controller.abort();
      window.clearTimeout(timeout);
      if (layer) map.removeLayer(layer);
      if (map.hasLayer(streets)) map.removeLayer(streets);
      delete map.getContainer().dataset.basemapError;
      delete map.getContainer().dataset.basemapKind;
      notice?.remove();
      onReady(null);
    };
  }, [map, onReady, attempt]);
  return null;
}
