/**
 * Native MCP client for the Anakin MCP server.
 *
 * Connects to @anakin-io/mcp over stdio using the official MCP SDK, so the
 * Mastra agent calls the real MCP server rather than re-implementing it.
 * The MCP process is spawned once and reused for every tool call.
 */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { CallToolResultSchema } from '@modelcontextprotocol/sdk/types.js';

let clientPromise: Promise<Client> | null = null;

function buildEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (typeof v === 'string') env[k] = v;
  }
  env.ANAKIN_API_KEY = process.env.ANAKIN_API_KEY ?? '';
  return env;
}

async function getClient(): Promise<Client> {
  if (!clientPromise) {
    clientPromise = (async () => {
      const transport = new StdioClientTransport({
        command: 'npx',
        args: ['-y', '@anakin-io/mcp@latest'],
        env: buildEnv(),
      });
      const client = new Client(
        { name: 'syndicate-mastra', version: '1.0.0' },
        { capabilities: {} },
      );
      await client.connect(transport);
      return client;
    })();
  }
  return clientPromise;
}

/** Call any Anakin MCP tool and return its parsed payload. */
export async function callAnakinTool(
  name: string,
  args: Record<string, unknown>,
): Promise<unknown> {
  const client = await getClient();
  // Low-level request instead of client.callTool(): the high-level helper
  // validates the response against each tool's declared outputSchema, and the
  // Anakin `search` tool returns extra properties that trip that validation
  // ("must NOT have additional properties"). CallToolResultSchema is the loose
  // envelope schema, which is what we actually want here.
  const res: any = await client.request(
    { method: 'tools/call', params: { name, arguments: args } },
    CallToolResultSchema,
  );
  const content = res?.content ?? [];
  for (const block of content) {
    if (block?.type === 'text' && typeof block.text === 'string') {
      try {
        return JSON.parse(block.text);
      } catch {
        return { raw_text: block.text };
      }
    }
  }
  return res;
}

/** List the tools the MCP server actually exposes (used by the tool test). */
export async function listAnakinTools(): Promise<string[]> {
  const client = await getClient();
  const res: any = await client.listTools();
  return (res?.tools ?? []).map((t: any) => t.name);
}

export async function closeAnakin(): Promise<void> {
  if (!clientPromise) return;
  try {
    const client = await clientPromise;
    await client.close();
  } catch {
    /* ignore */
  }
  clientPromise = null;
}