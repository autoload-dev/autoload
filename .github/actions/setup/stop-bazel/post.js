const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const modules = (process.env["INPUT_BAZEL-MODULES"] || ".")
  .split(/\r?\n/)
  .map((moduleRoot) => moduleRoot.trim())
  .filter(Boolean);
const shutdownSeconds = Number(process.env["INPUT_SHUTDOWN-TIMEOUT-SECONDS"]) || 30;

// Resolves to the exit status, the terminating signal or "timeout". A SIGTERM-only
// deadline can itself hang when the program ignores the signal. Kill only this
// child, never unrelated processes on the machine.
function tool(program, args, { visible = false, cwd, seconds = 3 } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(program, args, { cwd, stdio: visible ? "inherit" : "ignore" });
    let timedOut = false;
    const deadline = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, seconds * 1000);
    child.once("error", (error) => { clearTimeout(deadline); reject(error); });
    child.once("close", (status, signal) => {
      clearTimeout(deadline);
      resolve(timedOut ? "timeout" : status ?? signal);
    });
  });
}

async function shutdown(moduleRoot) {
  console.log(`Stopping Bazel in ${moduleRoot} (limit ${shutdownSeconds}s)`);
  let result;
  try {
    result = await tool("bazel", ["--noblock_for_lock", "shutdown"], {
      visible: true,
      cwd: path.resolve(process.env.GITHUB_WORKSPACE, moduleRoot),
      seconds: shutdownSeconds,
    });
  } catch (error) {
    console.log(`::warning::bazel shutdown in ${moduleRoot} failed: ${error}`);
    return;
  }
  if (result === "timeout") {
    console.log(`::warning::bazel shutdown in ${moduleRoot} timed out after ${shutdownSeconds}s; server may still be running; continuing cleanup`);
  } else if (result !== 0) {
    console.log(`::warning::bazel shutdown in ${moduleRoot} failed: ${result}`);
  } else {
    console.log(`Bazel stopped in ${moduleRoot}`);
  }
}

// A successful module shutdown does not cover servers from isolated proof output
// bases or orphaned workers after cancellation. Release the dedicated job mount,
// including mapped executables/libraries, before Sticky Disk's post action runs.
async function releaseCache(cachePath) {
  let cache = path.resolve(cachePath);
  if (cache === path.parse(cache).root) throw new Error("Refusing to clean filesystem root");
  if (await tool("mountpoint", ["-q", "--", cache]) !== 0) {
    console.log(`Repository cache ${cache} is not a mountpoint; skipping holder cleanup`);
    return;
  }
  cache = fs.realpathSync(cache);
  if (cache === path.parse(cache).root) throw new Error("Refusing to clean filesystem root");
  if (await tool("sudo", ["-n", "fuser", "-V"], { visible: true }) !== 0) {
    throw new Error("Cache cleanup requires noninteractive sudo and fuser");
  }
  // -M is a second, mandatory mountpoint guard on every filesystem-wide call.
  // No lazy unmount: real holders must exit before the cache can be committed.
  // PSmisc stops parsing entirely at -- instead of processing following paths.
  // cache is canonical and absolute, so it cannot be interpreted as an option.
  const fuser = (options, visible = false) => tool("sudo", ["-n", "fuser", "-m", "-M", ...options, cache], { visible });
  const occupied = async () => {
    const status = await fuser([]);
    if (status !== 0 && status !== 1) throw new Error(`Cannot inspect cache holders: ${status}`);
    return status === 0;
  };
  const waitForRelease = async () => {
    const deadline = Date.now() + 2000;
    do {
      if (!await occupied()) return true;
      await new Promise((resolve) => setTimeout(resolve, 100));
    } while (Date.now() < deadline);
    return false;
  };
  if (await occupied()) {
    console.log(`Processes still holding repository cache ${cache}:`);
    await fuser(["-v"], true);
    await fuser(["-k", "-TERM"], true);
    if (!await waitForRelease()) {
      console.log(`Force-stopping remaining repository cache holders in ${cache}`);
      await fuser(["-k", "-KILL"], true);
      if (!await waitForRelease()) throw new Error(`Repository cache remains busy: ${cache}`);
    }
  }
  console.log(`Repository cache released: ${cache}`);
}

async function main() {
  // Modules have independent servers, so one slow shutdown does not delay the others.
  await Promise.all(modules.map(shutdown));
  const cache = process.env["INPUT_REPOSITORY-CACHE"];
  if (cache) await releaseCache(cache);
}

main().catch((error) => {
  console.log(`::error::Bazel cleanup failed: ${error}`);
  process.exitCode = 1;
});
