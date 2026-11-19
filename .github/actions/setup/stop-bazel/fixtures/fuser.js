#!/usr/bin/env node
const fs = require("node:fs");
const args = process.argv.slice(2);
if (args.includes("-V")) process.exit(0);
fs.appendFileSync(process.env.FUSER_LOG, JSON.stringify(args) + "\n");
// PSmisc stops processing all arguments at --, ignoring the following path.
if (args.includes("--")) process.exit(1);
if (!fs.existsSync(process.env.CACHE_HOLDER)) process.exit(1);
if (args.includes("-KILL") || (args.includes("-TERM") && process.env.HOLDER_MODE !== "stubborn")) {
  fs.unlinkSync(process.env.CACHE_HOLDER);
}
process.exit(0);
