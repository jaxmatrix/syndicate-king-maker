/**
 * Verify the Anakin MCP tools make real calls and return real data.
 * Run: npx tsx tools_test.ts
 */
import './env.js';
import { listAnakinTools, callAnakinTool } from './anakin_mcp.js';

async function main() {
  console.log('ANAKIN_API_KEY set:', Boolean(process.env.ANAKIN_API_KEY));
  console.log('GOOGLE_MAPS_API_KEY set:', Boolean(process.env.GOOGLE_MAPS_API_KEY));

  const names = await listAnakinTools();
  console.log('\nMCP exposes', names.length, 'tools');
  console.log('sample:', names.slice(0, 15).join(', '));

  console.log('\n--- anakin-search (real web/reddit search) ---');
  const s: any = await callAnakinTool('search', {
    prompt: 'corporate catering complaints reddit',
    limit: 3,
  });
  const hits = s?.results ?? [];
  console.log('results:', hits.length);
  for (const h of hits) {
    console.log(' -', String(h.title ?? '').slice(0, 60));
    console.log('   ', String(h.url ?? '').slice(0, 90));
  }

  console.log('\n--- reddit wire read (real posts) ---');
  const r: any = await callAnakinTool('wire_read_action', {
    action_id: 'rt_subreddit_posts',
    params: { subreddit: 'restaurantowners', limit: 2 },
  });
  const posts = r?.data?.data?.posts ?? [];
  console.log('posts:', posts.length);
  for (const p of posts) {
    console.log(' -', String(p.title ?? '').slice(0, 70));
    console.log('   ', String(p.url ?? p.permalink ?? '').slice(0, 90));
  }

  const ok = hits.length > 0 && posts.length > 0;
  console.log('\nRESULT:', ok ? 'ANAKIN MCP TOOLS RETURN REAL DATA' : 'ANAKIN TOOLS FAILED');
  process.exit(ok ? 0 : 1);
}

main().catch((e) => {
  console.error('FAILED:', e);
  process.exit(1);
});