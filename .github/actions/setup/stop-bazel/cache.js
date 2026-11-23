const fs = require("node:fs");
const path = require("node:path");
const { tool, waitUntil } = require("./tool");

// A server shutdown does not cover servers from isolated output user roots or orphaned
// workers after cancellation. Release the dedicated job mount, including mapped
// executables/libraries, before Sticky Disk's post action runs.
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
  const waitForRelease = () => waitUntil(async () => !await occupied(), 2);
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

module.exports = { releaseCache };
