import { useState, useMemo, useCallback } from "react";
import Map, { Marker, Popup, NavigationControl } from "react-map-gl/maplibre";
import { X, MapPin as MapPinIcon, Building2 } from "lucide-react";
import "maplibre-gl/dist/maplibre-gl.css";

export interface Facility {
  name: string;
  city?: string;
  region?: string;
  facility_type?: string;
  lat: number;
  lon: number;
  [key: string]: unknown;
}

interface FacilitiesMapProps {
  facilities: Facility[];
  onClose: () => void;
}

/**
 * Jitter overlapping markers so they fan out around the shared position.
 * Facilities with unique lat/lon are untouched; duplicates get placed
 * in a small circle around the original point.
 */
function jitterOverlapping(facilities: Facility[]): (Facility & { _lat: number; _lon: number })[] {
  // Group by rounded lat/lon (5 decimal places ≈ 1m, so exact match means same spot)
  const groups: Record<string, number[]> = {};
  facilities.forEach((f, i) => {
    const key = `${f.lat.toFixed(5)},${f.lon.toFixed(5)}`;
    if (!groups[key]) groups[key] = [];
    groups[key].push(i);
  });

  return facilities.map((f, i) => {
    const key = `${f.lat.toFixed(5)},${f.lon.toFixed(5)}`;
    const group = groups[key];
    if (group.length <= 1) return { ...f, _lat: f.lat, _lon: f.lon };

    const indexInGroup = group.indexOf(i);
    const count = group.length;
    // Spread in a circle; radius ~0.003° ≈ 300m visual separation
    const angle = (2 * Math.PI * indexInGroup) / count;
    const radius = 0.003 * Math.min(count, 8) * 0.3; // scale slightly with count
    return {
      ...f,
      _lat: f.lat + radius * Math.cos(angle),
      _lon: f.lon + radius * Math.sin(angle),
    };
  });
}

// Free dark map style from CARTO
const MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

export default function FacilitiesMap({ facilities, onClose }: FacilitiesMapProps) {
  const [popupInfo, setPopupInfo] = useState<(Facility & { _lat: number; _lon: number }) | null>(null);

  const jittered = useMemo(() => jitterOverlapping(facilities), [facilities]);

  // Compute bounds to auto-fit
  const bounds = useMemo(() => {
    if (jittered.length === 0) return null;
    let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
    for (const f of jittered) {
      if (f._lat < minLat) minLat = f._lat;
      if (f._lat > maxLat) maxLat = f._lat;
      if (f._lon < minLon) minLon = f._lon;
      if (f._lon > maxLon) maxLon = f._lon;
    }
    return { minLat, maxLat, minLon, maxLon };
  }, [jittered]);

  const initialViewState = useMemo(() => {
    if (!bounds) return { latitude: 7.95, longitude: -1.03, zoom: 6 }; // Ghana center
    const centerLat = (bounds.minLat + bounds.maxLat) / 2;
    const centerLon = (bounds.minLon + bounds.maxLon) / 2;
    const latDiff = bounds.maxLat - bounds.minLat;
    const lonDiff = bounds.maxLon - bounds.minLon;
    const maxDiff = Math.max(latDiff, lonDiff, 0.01);
    // Rough zoom estimation
    const zoom = Math.min(Math.max(Math.log2(360 / maxDiff) - 1, 4), 14);
    return { latitude: centerLat, longitude: centerLon, zoom };
  }, [bounds]);

  const handleMarkerClick = useCallback((f: Facility & { _lat: number; _lon: number }) => {
    setPopupInfo(f);
  }, []);

  return (
    <div className="flex flex-col h-full bg-[var(--color-bg-secondary)] animate-fade-in">
      {/* Map Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[var(--color-step-icon-bg)]">
            <MapPinIcon size={14} className="text-[var(--color-accent)]" />
          </div>
          <div>
            <h3 className="text-[0.85rem] font-semibold text-[var(--color-text-primary)] leading-tight">
              Facility Map
            </h3>
            <p className="text-[0.65rem] text-[var(--color-text-muted)]">
              {facilities.length} facilit{facilities.length !== 1 ? "ies" : "y"} shown
            </p>
          </div>
        </div>
        <button
          id="close-map"
          onClick={onClose}
          className="flex items-center justify-center w-7 h-7 rounded-lg hover:bg-[var(--color-bg-hover)] transition-colors cursor-pointer text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
          aria-label="Close map"
        >
          <X size={16} />
        </button>
      </div>

      {/* Map */}
      <div className="flex-1 relative">
        <Map
          initialViewState={initialViewState}
          style={{ width: "100%", height: "100%" }}
          mapStyle={MAP_STYLE}
        >
          <NavigationControl position="top-right" />

          {jittered.map((f, i) => (
            <Marker
              key={`${f.name}-${i}`}
              latitude={f._lat}
              longitude={f._lon}
              anchor="bottom"
              onClick={(e) => {
                e.originalEvent.stopPropagation();
                handleMarkerClick(f);
              }}
            >
              <div className="cursor-pointer group flex flex-col items-center">
                <div className="w-7 h-7 rounded-full bg-[var(--color-accent)] border-2 border-white shadow-[0_0_12px_var(--color-accent-glow)] flex items-center justify-center group-hover:scale-110 transition-transform">
                  <Building2 size={13} className="text-white" />
                </div>
                {/* Small label on hover — hidden by default, shown on hover via CSS */}
                <div className="absolute -bottom-5 whitespace-nowrap bg-[var(--color-bg-primary)]/90 text-[0.6rem] text-[var(--color-text-primary)] px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none border border-[var(--color-border)]">
                  {f.name}
                </div>
              </div>
            </Marker>
          ))}

          {popupInfo && (
            <Popup
              latitude={popupInfo._lat}
              longitude={popupInfo._lon}
              anchor="bottom"
              closeOnClick={false}
              onClose={() => setPopupInfo(null)}
              className="facility-popup"
              offset={16}
            >
              <div className="p-2.5 min-w-[180px] max-w-[240px]">
                <h4 className="text-[0.82rem] font-semibold text-gray-900 leading-snug mb-1.5">
                  {popupInfo.name}
                </h4>
                <div className="space-y-1 text-[0.72rem] text-gray-600">
                  {popupInfo.facility_type && (
                    <p className="flex items-center gap-1.5">
                      <Building2 size={11} className="text-gray-400 flex-shrink-0" />
                      <span className="capitalize">{popupInfo.facility_type}</span>
                    </p>
                  )}
                  {popupInfo.city && (
                    <p className="flex items-center gap-1.5">
                      <MapPinIcon size={11} className="text-gray-400 flex-shrink-0" />
                      <span>{popupInfo.city}{popupInfo.region ? `, ${popupInfo.region}` : ""}</span>
                    </p>
                  )}
                  <p className="text-[0.65rem] text-gray-400 pt-1 border-t border-gray-200 mt-1">
                    {popupInfo.lat.toFixed(4)}, {popupInfo.lon.toFixed(4)}
                  </p>
                </div>
              </div>
            </Popup>
          )}
        </Map>

        {/* Duplicate coordinates notice */}
        {hasDuplicates(facilities) && (
          <div className="absolute bottom-3 left-3 right-3 bg-[var(--color-bg-primary)]/90 backdrop-blur-sm border border-[var(--color-border)] rounded-lg px-3 py-2 text-[0.7rem] text-[var(--color-text-muted)] flex items-start gap-2">
            <span className="text-[var(--color-warning)] mt-0.5 flex-shrink-0">⚠</span>
            <span>
              Some facilities share coordinates (city-level precision). Markers have been slightly
              spread apart for visibility.
            </span>
          </div>
        )}
      </div>

      {/* Footer list */}
      <div className="border-t border-[var(--color-border)] max-h-[140px] overflow-y-auto bg-[var(--color-bg-primary)]">
        {facilities.map((f, i) => (
          <button
            key={`${f.name}-${i}`}
            onClick={() => {
              const j = jittered[i];
              setPopupInfo(j);
            }}
            className="w-full flex items-center gap-2 px-4 py-2 text-left hover:bg-[var(--color-bg-hover)] transition-colors border-b border-[var(--color-border-step)] last:border-b-0 cursor-pointer"
          >
            <MapPinIcon size={12} className="text-[var(--color-accent)] flex-shrink-0" />
            <span className="text-[0.78rem] text-[var(--color-text-secondary)] truncate">{f.name}</span>
            {f.city && (
              <span className="ml-auto text-[0.68rem] text-[var(--color-text-muted)] flex-shrink-0">
                {f.city}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

function hasDuplicates(facilities: Facility[]): boolean {
  const seen = new Set<string>();
  for (const f of facilities) {
    const key = `${f.lat.toFixed(5)},${f.lon.toFixed(5)}`;
    if (seen.has(key)) return true;
    seen.add(key);
  }
  return false;
}
