/**
 * Live agent test: ask the agent something that REQUIRES tool calls and check it
 * actually invokes the real tools and grounds its answer in retrieved data.
 *
 * Run: npx tsx agent_test.ts
 */
import './env.js';
import { syndicateKingMakerAgent, MODEL_ID } from './agent.js';
import { listAnakinTools } from './anakin_mcp.js';

async function main() {
  console.log('model:', MODEL_ID);
  console.log('openrouter key:', Boolean(process.env.OPENROUTER_API_KEY));
  console.log('gmaps key:', Boolean(process.env.GOOGLE_MAPS_API_KEY));

  console.log('\n--- tools exposed by the Anakin MCP server ---');
  try {
    const names = await listAnakinTools();
    console.log(names.length, 'tools:', names.slice(0, 12).join(', '));
  } catch (e) {
    console.log('listTools failed:', (e as Error).message);
  }

  console.log('\n--- asking the agent to research a real place ---');
  const prompt =
    'Find coworking spaces within 800m of 37.7895,-122.3980 in San Francisco, ' +
    'then report the 3 closest with their exact coordinates. Cite what you used.';

  const res = await syndicateKingMakerAgent.generate(prompt);
  console.log('\n=== AGENT ANSWER ===');
  console.log(res.text);

  const calls = (res as any).toolCalls ?? [];
  console.log('\n=== TOOL CALLS ===');
  console.log('count:', calls.length);
  for (const c of calls) {
    const name = c?.payload?.toolName ?? c?.toolName ?? '?';
    console.log(' -', name, JSON.stringify(c?.payload?.args ?? {}).slice(0, 120));
  }

  const usedReal = calls.some((c: any) => {
    const n = String(c?.payload?.toolName ?? c?.toolName ?? '');
    return n.includes('google') || n.includes('anakin');
  });
  console.log('\nRESULT:', usedReal ? 'AGENT MADE REAL TOOL CALLS' : 'NO REAL TOOL CALLS (check agent)');
  process.exit(usedReal ? 0 : 1);
}

main().catch((e) => {
  console.error('FAILED:', e);
  process.exit(1);
});