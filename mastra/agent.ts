/**
 * Syndicate King Maker - live research agent.
 *
 * Every tool on this agent makes a real call: Anakin MCP over stdio, or the
 * Google Maps APIs. The previous revision of this file returned hardcoded fake
 * buildings (lat + 0.002), invented pain signals and stub subreddits - that
 * fabrication has been deleted, in line with the engine's "no invented data"
 * invariant.
 */
import './env.js'; // must precede any module that reads process.env at import time
import { Agent } from '@mastra/core/agent';
import { createOpenAI } from '@ai-sdk/openai';
import { anakinSearchTool, anakinRedditPostsTool, anakinScrapeTool } from './tools_anakin.js';
import { googlePlacesTool, googleGeocodeTool } from './tools_maps.js';

// OpenRouter is OpenAI-compatible, so the OpenAI provider works with a baseURL swap.
const openrouter = createOpenAI({
  baseURL: 'https://openrouter.ai/api/v1',
  apiKey: process.env.OPENROUTER_API_KEY ?? '',
});

// Verified available and reliable for strict-JSON work with citations.
// Do NOT use google/gemini-3.7-flash: it is a reasoning model that returns
// content: null, which breaks structured output.
export const MODEL_ID = process.env.SYNDICATE_LLM_MODEL ?? 'deepseek/deepseek-v4.1-flash';

export const syndicateKingMakerAgent = new Agent({
  id: 'syndicate-king-maker',
  name: 'Syndicate King Maker',
  instructions: `
You are the chief commercial expansion and site-selection research agent for Syndicate.

You work only from real retrieved data. You have these tools:
- google-geocode: turn a place name or city into real coordinates.
- google-places-nearby: find real businesses/offices/cafes within a radius of a coordinate.
- anakin-search: search the live web and Reddit for a sector, competitor, pricing or hiring signal.
- anakin-reddit-posts: read real posts from a subreddit.
- anakin-scrape: read a specific page or thread in full.

HARD RULES:
1. NEVER invent facts, names, numbers, coordinates or sources. If a tool did not
   return it, you do not know it.
2. Every claim you make must name the source url that produced it.
3. Coordinates must come from a tool call, never estimated.
4. If a tool returns nothing, say plainly that the data was not found. Do not fill
   the gap with plausible wording.
5. Prefer doing the work over describing it: if the user asks you to research an
   area, geocode it, then search places around it, then report what you actually
   found.

When the user asks you to find new customers or expand a scan, chain the tools:
geocode the area -> places-nearby for the ICP's buildings -> anakin-search for
that sector's buying signals -> report findings with urls and coordinates.
`,
  // .chat() pins the chat-completions endpoint; the bare callable defaults to
  // OpenRouter's /responses route, which does not serve this model.
  model: openrouter.chat(MODEL_ID),
  tools: {
    anakinSearchTool,
    anakinRedditPostsTool,
    anakinScrapeTool,
    googlePlacesTool,
    googleGeocodeTool,
  },
});
