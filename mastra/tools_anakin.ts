/**
 * Anakin MCP tools for the Mastra agent - REAL calls, no synthesised data.
 *
 * Each tool delegates to the Anakin MCP server over stdio via anakin_mcp.ts.
 */
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';
import { callAnakinTool } from './anakin_mcp.js';

export const anakinSearchTool = createTool({
  id: 'anakin-search',
  description:
    'Search the live web (including Reddit and news) via the Anakin MCP. Returns real ' +
    'result title, snippet and url. Use this to research a sector, find complaints, ' +
    'competitors, pricing or hiring signals. Always report the source urls.',
  inputSchema: z.object({
    query: z.string().describe('Natural-language search query'),
    limit: z.number().int().min(1).max(10).default(5),
  }),
  execute: async ({ query, limit }) => {
    const res: any = await callAnakinTool('search', { prompt: query, limit });
    const results = (res?.results ?? []).map((r: any) => ({
      title: r.title ?? '',
      snippet: r.snippet ?? '',
      url: r.url ?? r.link ?? '',
      date: r.date ?? '',
    }));
    return { count: results.length, results };
  },
});

export const anakinRedditPostsTool = createTool({
  id: 'anakin-reddit-posts',
  description:
    'Read real posts from a subreddit via the Anakin MCP reddit action. Returns post ' +
    'titles, bodies and permalinks. Use it to gather genuine practitioner complaints ' +
    'and buying intent for an ICP.',
  inputSchema: z.object({
    subreddit: z.string().describe('Subreddit name without the r/ prefix'),
    limit: z.number().int().min(1).max(10).default(5),
  }),
  execute: async ({ subreddit, limit }) => {
    const res: any = await callAnakinTool('wire_read_action', {
      action_id: 'rt_subreddit_posts',
      params: { subreddit, limit },
    });
    const posts = res?.data?.data?.posts ?? [];
    return {
      subreddit,
      count: posts.length,
      posts: posts.slice(0, limit).map((p: any) => ({
        title: p.title ?? '',
        body: String(p.selftext ?? '').slice(0, 600),
        url: p.url ?? (p.permalink ? `https://www.reddit.com${p.permalink}` : ''),
        date: p.created_utc ?? '',
      })),
    };
  },
});

export const anakinScrapeTool = createTool({
  id: 'anakin-scrape',
  description:
    'Scrape a specific page (e.g. a Reddit thread permalink, a competitor pricing ' +
    'page, a job listing) via the Anakin MCP and return clean markdown. Use it to read ' +
    'a source in full before quoting it.',
  inputSchema: z.object({
    url: z.string().url().describe('Absolute http(s) url to scrape'),
  }),
  execute: async ({ url }) => {
    const res: any = await callAnakinTool('scrape', {
      url,
      generateJson: false,
      useBrowser: false,
    });
    const markdown = res?.markdown ?? res?.data?.markdown ?? '';
    return { url, chars: String(markdown).length, markdown: String(markdown).slice(0, 6000) };
  },
});
