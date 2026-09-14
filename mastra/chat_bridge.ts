/**
 * Live chat bridge for the Mastra agent.
 *
 * The deployed browser cannot reach a localhost port, so - exactly like the
 * research queue - it posts a pending row to Helix and polls for the reply.
 * This bridge polls that queue, runs the real Mastra agent (which calls the
 * Anakin MCP and Google Maps tools), and writes the answer back.
 *
 * Run: npx tsx chat_bridge.ts   (or via workspace_watchdog)
 */
import './env.js';
import http from 'node:http';
import https from 'node:https';
import { syndicateKingMakerAgent } from './agent.js';

const HELIX = process.env.HELIX_GATEWAY_URL ?? 'http://helix:8080';
const APP_HOST = 'syndicate-app.jai.allr.work';
const PATH = '/api/chat';
const POLL_MS = 2000;

const seen = new Set<string>();

function log(msg: string) {
  console.log(`${new Date().toISOString()} [chat_bridge] ${msg}`);
}

/**
 * Helix routes by Host header, and undici's fetch() silently DROPS the Host
 * header because it is a forbidden header name - every request 404s. Using
 * node:http lets us set Host explicitly, matching what the Python clients do.
 */
function helixJson(method: string, body?: unknown): Promise<any> {
  return new Promise((resolve, reject) => {
    const url = new URL(HELIX);
    const payload = body ? JSON.stringify(body) : undefined;
    const mod = url.protocol === 'https:' ? https : http;
    const req = mod.request(
      {
        hostname: url.hostname,
        port: url.port || (url.protocol === 'https:' ? 443 : 80),
        path: PATH,
        method,
        headers: {
          Host: APP_HOST,
          Accept: 'application/json',
          ...(payload
            ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }
            : {}),
        },
      },
      (res) => {
        let raw = '';
        res.on('data', (c) => (raw += c));
        res.on('end', () => {
          if (!res.statusCode || res.statusCode >= 400) {
            reject(new Error(`HTTP ${res.statusCode}`));
            return;
          }
          try {
            resolve(raw ? JSON.parse(raw) : {});
          } catch (e) {
            reject(e as Error);
          }
        });
      },
    );
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

async function pending(): Promise<any[]> {
  try {
    const data = await helixJson('GET');
    const rows = Array.isArray(data) ? data : data?.data ?? [];
    return rows.filter((r: any) => r?.status === 'pending' && !seen.has(r.id));
  } catch (e) {
    console.error('poll error:', (e as Error).message);
    return [];
  }
}

/** Compose the agent prompt: prior scan context first, then the user's ask. */
function buildPrompt(message: string, context: string): string {
  let ctx = '';
  try {
    const parsed = JSON.parse(context || '{}');
    if (parsed && Object.keys(parsed).length) {
      ctx =
        'CONTEXT from the most recent research scan in this workspace ' +
        '(use it; you may extend it with tool calls):\n' +
        JSON.stringify(parsed).slice(0, 4000) +
        '\n\n';
    }
  } catch {
    /* no usable context */
  }
  return `${ctx}USER REQUEST:\n${message}`;
}

async function handle(row: any): Promise<void> {
  const id = row.id;
  seen.add(id);
  log(`handling ${id}: ${String(row.message).slice(0, 70)}`);

  let reply = '';
  let toolCalls: unknown[] = [];
  try {
    const res = await syndicateKingMakerAgent.generate(
      buildPrompt(row.message ?? '', row.context ?? '{}'),
    );
    reply = res.text ?? '';
    toolCalls = ((res as any).toolCalls ?? []).map((c: any) => ({
      tool: c?.payload?.toolName ?? c?.toolName ?? 'unknown',
      args: c?.payload?.args ?? {},
    }));
  } catch (e) {
    reply = `The research agent could not complete this request: ${(e as Error).message}`;
  }

  try {
    await helixJson('POST', {
      id: crypto.randomUUID(),
      user_id: row.user_id ?? 'guest',
      message: row.message ?? '',
      context: row.context ?? '{}',
      reply,
      tool_calls: JSON.stringify(toolCalls),
      status: `replied:${id}`,
      created_at: new Date().toISOString(),
    });
    log(`replied to ${id} (${toolCalls.length} tool call(s))`);
  } catch (e) {
    log(`failed to publish reply for ${id}: ${(e as Error).message}`);
  }
}

async function main() {
  log(`chat bridge up (queue ${PATH})`);
  for (;;) {
    const rows = await pending();
    for (const row of rows) {
      await handle(row);
    }
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
}

main().catch((e) => {
  console.error('bridge crashed:', e);
  process.exit(1);
});