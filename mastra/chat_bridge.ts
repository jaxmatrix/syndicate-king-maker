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

// Only claim pending rows newer than this. Completion is published as a separate
// reply row rather than clearing the original, so without a freshness window a
// bridge restart would re-run every historical request and delay new ones behind
// that backlog.
const MAX_PENDING_AGE_S = Number(process.env.SYNDICATE_PENDING_MAX_AGE_S ?? 1800);

const seen = new Set<string>();

function log(msg: string) {
  console.log(`${new Date().toISOString()} [chat_bridge] ${msg}`);
}

/** True when a pending row is recent enough to be worth answering. */
function isFresh(row: any): boolean {
  const raw = String(row?.created_at ?? '');
  if (!raw) return false;
  const ts = Date.parse(raw);
  if (Number.isNaN(ts)) return false;
  const ageS = (Date.now() - ts) / 1000;
  return ageS >= 0 && ageS <= MAX_PENDING_AGE_S;
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
    return rows.filter((r: any) =>
      r?.status === 'pending' && !seen.has(r.id) && isFresh(r));
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

/**
 * Publish one action line for a chat turn in progress.
 *
 * Uses its own status prefix so the client can render these live, in order,
 * while the agent works - the queue has no update operation, so progress is a
 * separate append-only record.
 */
async function publishProgress(chatId: string, userId: string, label: string) {
  try {
    await helixJson('POST', {
      id: crypto.randomUUID(),
      user_id: userId,
      message: '',
      context: '{}',
      reply: label,
      tool_calls: '[]',
      status: `cprogress:${chatId}`,
      created_at: new Date().toISOString(),
    });
    log(`[${chatId.slice(0, 8)}] ${label}`);
  } catch (e) {
    log(`progress publish failed: ${(e as Error).message}`);
  }
}

/** Summarise a tool call so the user sees what was invoked, not just that something was. */
function describeTool(name: string, args: unknown): string {
  const a = (args ?? {}) as Record<string, unknown>;
  const bits: string[] = [];
  if (a.query) bits.push(`"${String(a.query).slice(0, 60)}"`);
  if (a.address) bits.push(`"${String(a.address).slice(0, 50)}"`);
  if (a.subreddit) bits.push(`r/${a.subreddit}`);
  if (a.url) bits.push(String(a.url).slice(0, 70));
  if (a.keyword) bits.push(`"${a.keyword}"`);
  if (a.lat != null && a.lng != null) bits.push(`@${a.lat},${a.lng}`);
  if (a.radiusMeters != null) bits.push(`r=${a.radiusMeters}m`);
  return bits.length ? `${name}(${bits.join(', ')})` : name;
}

async function handle(row: any): Promise<void> {
  const id = row.id;
  const userId = row.user_id ?? 'guest';
  seen.add(id);
  log(`handling ${id}: ${String(row.message).slice(0, 70)}`);
  await publishProgress(id, userId, `Request received · analysing`);

  let reply = '';
  let toolCalls: unknown[] = [];
  let stepNo = 0;
  try {
    const res = await syndicateKingMakerAgent.generate(
      buildPrompt(row.message ?? '', row.context ?? '{}'),
      {
        // Log every step as it happens so the user sees the agent working
        // rather than waiting on a silent spinner.
        onStepFinish: async (event: any) => {
          stepNo += 1;
          const results = event?.toolResults ?? [];
          if (results.length) {
            for (const tr of results) {
              const name = tr?.toolName ?? tr?.payload?.toolName ?? 'tool';
              const args = tr?.args ?? tr?.payload?.args ?? {};
              await publishProgress(id, userId, `Step ${stepNo} · calling ${describeTool(name, args)}`);
            }
          } else {
            const text = event?.stepResult?.text ?? event?.stepResult?.reasoning ?? '';
            if (text) {
              await publishProgress(id, userId,
                `Step ${stepNo} · ${String(text).replace(/\s+/g, ' ').slice(0, 140)}`);
            }
          }
        },
      },
    );
    reply = res.text ?? '';
    toolCalls = ((res as any).toolCalls ?? []).map((c: any) => ({
      tool: c?.payload?.toolName ?? c?.toolName ?? 'unknown',
      args: c?.payload?.args ?? {},
    }));
  } catch (e) {
    reply = `The research agent could not complete this request: ${(e as Error).message}`;
    await publishProgress(id, userId, `Agent error · ${(e as Error).message}`);
  }

  await publishProgress(id, userId,
    `Composing answer · ${toolCalls.length} tool call(s) completed`);

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