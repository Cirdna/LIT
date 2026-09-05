// Load .env into process.env for the runtime processes (API, stub worker, seed).
// The Prisma *CLI* loads .env on its own, but Prisma *Client* and our config read
// process.env directly, so long-running scripts must load it themselves. Import
// this FIRST, before anything that reads env (config, the Prisma client).
//
// Uses Node's built-in loader (>= 20.12) so there is no dependency to install.
try {
  process.loadEnvFile();
} catch {
  // No .env file present — fall back to the real environment.
}
