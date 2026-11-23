// A fake Bazel server: named by its --output_base argument like a real one, it records its PID
// in the output base and runs until signaled. A stubborn server ignores SIGTERM.
const fs = require("node:fs");
const path = require("node:path");

const [outputBase, mode] = process.argv.slice(2);
const serverDir = path.join(outputBase.replace(/^--output_base=/, ""), "server");
fs.mkdirSync(serverDir, { recursive: true });
if (mode === "stubborn") process.on("SIGTERM", () => {});
fs.writeFileSync(path.join(serverDir, "server.pid.txt"), String(process.pid));
setInterval(() => {}, 1000);
