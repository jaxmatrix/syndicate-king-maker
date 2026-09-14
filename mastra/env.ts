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

dotenv.config({ path: '/opt/data/profiles/accelerator/.env' });
dotenv.config({ path: '/opt/data/.env' });
dotenv.config(); // local .env, if any