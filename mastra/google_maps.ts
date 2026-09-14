/**
 * Real Google Maps API helpers used by the Mastra agent's tools.
 *
 * Every call returns data straight from Google (Places / Geocoding), each place
 * carrying the exact `geometry.location` for its own place_id. Nothing here
 * synthesises coordinates: the same place always resolves to the same pin.
 */

const KEY = process.env.GOOGLE_MAPS_API_KEY ?? '';

export function mapsKeyPresent(): boolean {
  return KEY.length > 0;
}

/** Great-circle distance in metres. */
export function haversineM(
  lat1: number, lng1: number, lat2: number, lng2: number,
): number {
  const R = 6371008.8;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dPhi = p2 - p1;
  const dLambda = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(dLambda / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

async function getJson(url: string): Promise<any> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} from Google Maps`);
  return res.json();
}

export interface PlaceResult {
  placeId: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
  distanceMeters: number;
  rating: number | null;
  userRatingsTotal: number;
}

/** Places Nearby Search, hard-filtered to the radius by haversine. */
export async function placesNearby(
  lat: number,
  lng: number,
  radiusMeters: number,
  keyword: string,
  limit = 20,
): Promise<PlaceResult[]> {
  if (!KEY) throw new Error('GOOGLE_MAPS_API_KEY is not set');

  const radius = Math.min(Math.max(Math.round(radiusMeters || 1500), 100), 50000);
  const url =
    'https://maps.googleapis.com/maps/api/place/nearbysearch/json' +
    `?location=${lat},${lng}&radius=${radius}` +
    `&keyword=${encodeURIComponent(keyword)}&key=${KEY}`;

  const data = await getJson(url);
  const out: PlaceResult[] = [];
  for (const r of data.results ?? []) {
    const loc = r?.geometry?.location;
    if (!r?.place_id || loc?.lat == null || loc?.lng == null) continue;
    const distanceMeters = haversineM(lat, lng, loc.lat, loc.lng);
    if (distanceMeters > radius) continue; // outside the scan circle
    out.push({
      placeId: r.place_id,
      name: r.name ?? '',
      address: r.vicinity ?? r.formatted_address ?? '',
      lat: loc.lat,
      lng: loc.lng,
      distanceMeters: Math.round(distanceMeters),
      rating: r.rating ?? null,
      userRatingsTotal: r.user_ratings_total ?? 0,
    });
    if (out.length >= limit) break;
  }
  out.sort((a, b) => a.distanceMeters - b.distanceMeters);
  return out;
}

export interface GeocodeResult {
  formattedAddress: string;
  lat: number;
  lng: number;
  types: string[];
}

/** Geocoding lookup - resolves a place name or address to real coordinates. */
export async function geocode(address: string): Promise<GeocodeResult | null> {
  if (!KEY) throw new Error('GOOGLE_MAPS_API_KEY is not set');
  const url =
    'https://maps.googleapis.com/maps/api/geocode/json' +
    `?address=${encodeURIComponent(address)}&key=${KEY}`;
  const data = await getJson(url);
  const first = (data.results ?? [])[0];
  if (!first?.geometry?.location) return null;
  return {
    formattedAddress: first.formatted_address ?? address,
    lat: first.geometry.location.lat,
    lng: first.geometry.location.lng,
    types: first.types ?? [],
  };
}