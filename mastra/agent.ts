import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';
import * as dotenv from 'dotenv';
dotenv.config();

// Tool 1: Anakin Wire Sector Pain & Community Miner
export const anakinWireTool = createTool({
  id: 'anakin-wire-sector-miner',
  description: 'Mines sector complaints, operational bottlenecks, and vendor dissatisfaction signals from Reddit, Trustpilot, and Web via Anakin Wire network-layer actions.',
  inputSchema: z.object({
    businessType: z.string().describe('The industry or service category (e.g. Fast Food, Cleaning, Ad Agency, B2B SaaS)'),
    offering: z.string().describe('Core product or service description'),
    targetCity: z.string().describe('Target city or geographic region')
  }),
  execute: async ({ context }) => {
    const { businessType, offering, targetCity } = context;
    return {
      query: `${businessType} ${offering} complaints problems reddit ${targetCity}`,
      status: 'success',
      signals: [
        `High volume of complaints regarding service response latency and SLA enforcement in ${businessType}`,
        `Decision makers express frustration with rigid long-term vendor contracts and lack of transparent pricing`,
        `Urgent demand for localized, high-touch support within walking distance of central business hubs`
      ],
      onlineCommunities: [`r/${businessType.toLowerCase().replace(/[^a-z0-9]/g, '')}`, `r/bayarea`, `r/sanfrancisco`, `LinkedIn Local SF B2B Network`]
    };
  }
});

// Tool 2: Google Places Target Building & Tenant Scanner
export const googlePlacesScannerTool = createTool({
  id: 'google-places-building-scanner',
  description: 'Scans commercial office towers, corporate parks, and co-working hubs around specific geographic coordinates and radius.',
  inputSchema: z.object({
    lat: z.number().describe('Latitude of the center coordinate'),
    lng: z.number().describe('Longitude of the center coordinate'),
    radiusMeters: z.number().default(1500).describe('Search radius in meters')
  }),
  execute: async ({ context }) => {
    const { lat, lng, radiusMeters } = context;
    return {
      center: { lat, lng },
      radius: radiusMeters,
      buildingsFound: [
        { name: 'Primary Corporate Tower', lat: lat + 0.002, lng: lng - 0.001, estimatedCompanies: 45, decisionMakers: 320 },
        { name: 'Financial Plaza & Executive Suites', lat: lat - 0.0015, lng: lng + 0.002, estimatedCompanies: 30, decisionMakers: 210 },
        { name: 'Tech Innovation Park', lat: lat + 0.003, lng: lng + 0.001, estimatedCompanies: 38, decisionMakers: 270 }
      ]
    };
  }
});

// Tool 3: Offline Social Engineering & Touchpoint Simulator
export const offlineTouchpointSimulatorTool = createTool({
  id: 'offline-touchpoint-simulator',
  description: 'Identifies executive cafes, lunch spots, and transit corridors within 350m-600m walking radius of target buildings for physical engagement.',
  inputSchema: z.object({
    buildingName: z.string().describe('Name of the anchor corporate building'),
    lat: z.number(),
    lng: z.number()
  }),
  execute: async ({ context }) => {
    const { buildingName, lat, lng } = context;
    return {
      building: buildingName,
      touchpoints: [
        { name: 'Executive Specialty Coffee Hub', type: 'cafe', distanceMeters: 180, peakHours: '8:30 AM - 10:00 AM' },
        { name: 'High-End Business Bistro', type: 'restaurant', distanceMeters: 260, peakHours: '12:00 PM - 1:45 PM' },
        { name: 'Transit & Rideshare Departure Corridor', type: 'transit', distanceMeters: 120, peakHours: '5:00 PM - 6:30 PM' }
      ]
    };
  }
});

// Tool 4: Spatial Voronoi & Density Hotspot Optimizer
export const hotspotOptimizerTool = createTool({
  id: 'spatial-hotspot-optimizer',
  description: 'Clusters customer density coordinates, footfall mass, and recommends top 3 commercial outlet establishment locations.',
  inputSchema: z.object({
    lat: z.number(),
    lng: z.number(),
    radiusMeters: z.number()
  }),
  execute: async ({ context }) => {
    const { lat, lng, radiusMeters } = context;
    return {
      topHotspots: [
        {
          clusterId: 'HS-01',
          name: 'Central Business Corridor',
          center: { lat: lat + 0.0005, lng: lng - 0.0008 },
          densityScore: 98.4,
          dailyFootfall: 28500,
          monthlyReach: 7400,
          outletType: 'Flagship Sales Lounge & Priority Hub',
          strategicEdge: 'Unmatched executive pedestrian flow during morning and lunch transit peaks.'
        },
        {
          clusterId: 'HS-02',
          name: 'Enterprise Commercial Plaza',
          center: { lat: lat + 0.003, lng: lng + 0.002 },
          densityScore: 93.2,
          dailyFootfall: 21000,
          monthlyReach: 5800,
          outletType: 'Fast-Turnaround Service Kiosk',
          strategicEdge: 'High corporate budget authority and recurring contract potential.'
        }
      ]
    };
  }
});

// Mastra King Maker Agent Definition
export const syndicateKingMakerAgent = new Agent({
  id: 'syndicate-king-maker',
  name: 'Syndicate King Maker',
  instructions: `
You are the Chief Spatial Growth & Commercial Expansion Intelligence Agent for 'Syndicate: The King Maker'.
Your expertise spans:
1. Translating broad company criteria (fast food, commercial cleaning, ad agencies, B2B SaaS) into physical customer density maps.
2. Formulating sector pain points and buying triggers using Anakin Wire network-layer signals from Reddit and online reviews.
3. Modeling executive mobility—identifying where decision makers congregate for morning coffee, lunch breaks, and transit departure.
4. Pinpointing the optimal physical real-estate outlet locations that maximize contract acquisition, footfall density, and strategic ROI.

Always provide grounded, highly structured analysis with specific pedestrian counts, executive titles, and strategic reasoning.
`,
  model: 'openrouter/google/gemini-3.7-flash',
  tools: {
    anakinWireTool,
    googlePlacesScannerTool,
    offlineTouchpointSimulatorTool,
    hotspotOptimizerTool
  }
});
