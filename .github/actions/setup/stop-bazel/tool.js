const { spawn } = require("node:child_process");

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

// Resolves to true once the predicate holds, checking every 100 ms, or to false at the deadline.
async function waitUntil(predicate, seconds) {
  const deadline = Date.now() + seconds * 1000;
  do {
    if (await predicate()) return true;
    await new Promise((resolve) => setTimeout(resolve, 100));
  } while (Date.now() < deadline);
  return false;
}

module.exports = { tool, waitUntil };
