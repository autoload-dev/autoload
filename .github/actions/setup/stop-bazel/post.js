const { execFile } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");
const { promisify } = require("node:util");
const { releaseCache } = require("./cache");
const { tool } = require("./tool");

const shutdownSeconds = Number(process.env["INPUT_SHUTDOWN-TIMEOUT-SECONDS"]) || 30;

// Bazel's default output user root on Linux: <cache>/bazel/_bazel_<user>, with the cache
// directory and the user name resolved as the Bazel client resolves them.
function outputUserRoot() {
  const cache = process.env.XDG_CACHE_HOME || path.join(process.env.HOME || os.homedir(), ".cache");
  return path.join(cache, "bazel", `_bazel_${process.env.USER || os.userInfo().username}`);
}

// Every output base under the output user root with a server PID file, whichever workspace
// or job step started it: no workflow lists the modules it ran Bazel in. Bazel records the
// workspace of an output base in its DO_NOT_BUILD_HERE file.
function servers(root) {
  let entries;
  try {
    entries = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return [];
  }
  return entries.filter((entry) => entry.isDirectory()).flatMap((entry) => {
    const outputBase = path.join(root, entry.name);
    const read = (file) => {
      try { return fs.readFileSync(path.join(outputBase, file), "utf8").trim(); }
      catch { return ""; }
    };
    const pid = Number(read("server/server.pid.txt"));
    if (!Number.isInteger(pid) || pid <= 0) return [];
    return [{ outputBase, pid, workspace: read("DO_NOT_BUILD_HERE") }];
  });
}

// The server still runs while its PID belongs to a process started for its output base:
// Bazel passes --output_base to the server. A recycled PID never matches.
async function running({ pid, outputBase }) {
  let args;
  try {
    ({ stdout: args } = await promisify(execFile)("ps", ["-ww", "-o", "args=", "-p", String(pid)], {
      timeout: 3000, killSignal: "SIGKILL",
    }));
  } catch {
    return false;
  }
  return args.trim().split(/\s+/).includes(`--output_base=${outputBase}`);
}

async function exited(server, seconds) {
  const deadline = Date.now() + seconds * 1000;
  do {
    if (!await running(server)) return true;
    await new Promise((resolve) => setTimeout(resolve, 100));
  } while (Date.now() < deadline);
  return false;
}

async function bazelShutdown({ outputBase, workspace }) {
  const name = path.basename(outputBase);
  if (!workspace || !fs.existsSync(workspace)) {
    console.log(`::warning::workspace of Bazel server ${name} is gone; stopping its process`);
    return false;
  }
  console.log(`Stopping Bazel server ${name} of ${workspace} (limit ${shutdownSeconds}s)`);
  let result;
  try {
    result = await tool("bazel", [`--output_base=${outputBase}`, "--noblock_for_lock", "shutdown"], {
      visible: true,
      cwd: workspace,
      seconds: shutdownSeconds,
    });
  } catch (error) {
    result = error;
  }
  if (result === "timeout") {
    console.log(`::warning::bazel shutdown of ${workspace} timed out after ${shutdownSeconds}s; continuing cleanup`);
  } else if (result !== 0) {
    console.log(`::warning::bazel shutdown of ${workspace} failed: ${result}`);
  }
  return result === 0;
}

// A graceful shutdown first, so the server stops its persistent workers. A server that
// survives it, or whose workspace is gone, gets SIGTERM and then SIGKILL.
async function shutdown(server) {
  if (!await running(server)) return;
  const stopped = (await bazelShutdown(server) && await exited(server, 3)) || await terminate(server);
  console.log(stopped
    ? `Bazel stopped: ${server.outputBase}`
    : `::warning::Bazel server ${server.pid} of ${server.outputBase} is still running`);
}

async function terminate(server) {
  for (const signal of ["SIGTERM", "SIGKILL"]) {
    console.log(`Sending ${signal} to Bazel server ${server.pid} of ${server.outputBase}`);
    try { process.kill(server.pid, signal); } catch (error) { if (error.code !== "ESRCH") throw error; }
    if (await exited(server, 3)) return true;
  }
  return false;
}

async function main() {
  // A persistent runner keeps its Bazel servers warm between jobs on purpose; the
  // workflow runs this step only on fresh Linux runners, and the step checks again.
  if (process.env.RUNNER_OS !== "Linux" || process.env.PERSISTENT_RUNNER === "true") {
    console.log("Not a fresh Linux runner; leaving Bazel servers running");
    return;
  }
  const root = outputUserRoot();
  const found = servers(root);
  console.log(`Found ${found.length} Bazel server(s) under ${root}`);
  // Servers are independent, so one slow shutdown does not delay the others.
  await Promise.all(found.map(shutdown));
  const cache = process.env["INPUT_REPOSITORY-CACHE"];
  if (cache) await releaseCache(cache);
}

main().catch((error) => {
  console.log(`::error::Bazel cleanup failed: ${error}`);
  process.exitCode = 1;
});
