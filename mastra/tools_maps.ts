/**
 * Google Maps API tools for the Mastra agent - REAL calls via google_maps.ts.
 *
 * Returned coordinates come straight from Google for each place_id, so a place
 * always resolves to the same pin regardless of the query that found it.
 */
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';
import { placesNearby, geocode } from './google_maps.js';

export const googlePlacesTool = createTool({
  id: 'google-places-nearby',
  description:
    'Find real commercial places (office buildings, coworking spaces, cafes, ' +
    'restaurants, factories) within a radius of a coordinate, using the Google Places ' +
    'API. Returns exact coordinates and distances. Use it to locate where a target ICP ' +
    'physically is, or where to place an outlet.',
  inputSchema: z.object({
    lat: z.number().describe('Latitude of the centre point'),
    lng: z.number().describe('Longitude of the centre point'),
    radiusMeters: z.number().min(100).max(50000).default(1500),
    keyword: z.string().describe('What to look for, e.g. "office building", "coworking", "cafe"'),
    limit: z.number().int().min(1).max(40).default(20),
  }),
  execute: async ({ lat, lng, radiusMeters, keyword, limit }) => {
    const places = await placesNearby(lat, lng, radiusMeters, keyword, limit);
    return {
      centre: { lat, lng },
      radiusMeters,
      keyword,
      count: places.length,
      places,
    };
  },
});

export const googleGeocodeTool = createTool({
  id: 'google-geocode',
  description:
    'Resolve a place name, address or city to real coordinates using the Google ' +
    'Geocoding API. Use this to turn a user\'s stated target area into a lat/lng anchor ' +
    'before running any spatial search.',
  inputSchema: z.object({
    address: z.string().describe('Address, city or place name, e.g. "SoMa, San Francisco"'),
  }),
  execute: async ({ address }) => {
    const result = await geocode(address);
    if (!result) return { found: false, address };
    return { found: true, ...result };
  },
});
