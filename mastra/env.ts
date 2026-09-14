/**
 * Environment bootstrap.
 *
 * Must be imported BEFORE any module that reads process.env at import time.
 * ES module imports are hoisted and evaluated in order, so `import './env.js'`
 * placed first in agent.ts guarantees the keys exist by the time the agent
 * constructs its model client.
 *
 * The worker/watchdog environment does not carry these keys, which is why we
 * read the shared .env file explicitly rather than trusting the process env.
 */
import * as dotenv from 'dotenv';

// App-specific secrets FIRST (they must win for Syndicate), then the shared
// files as fallback. dotenv does not override already-set keys, so this order
// means Syndicate uses its own OPENROUTER_API_KEY without affecting the Allr
// agent's own key in the shared profile env.
dotenv.config({ path: '/opt/data/syndicate/.env' });
dotenv.config({ path: '/opt/data/profiles/accelerator/.env' });
dotenv.config({ path: '/opt/data/.env' });
dotenv.config(); // local .env, if any