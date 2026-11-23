const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");

function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "bazel-cleanup-")));
  t.after(() => {
    const pidFile = path.join(root, "hanging.pid");
    if (fs.existsSync(pidFile)) {
      try { process.kill(Number(fs.readFileSync(pidFile, "utf8")), "SIGKILL"); }
      catch (error) { if (error.code !== "ESRCH") throw error; }
    }
    fs.rmSync(root, { recursive: true, force: true });
  });
  const bin = path.join(root, "bin");
  fs.mkdirSync(bin);
  fs.copyFileSync(path.join(__dirname, "fixtures/bazel.sh"), path.join(bin, "bazel"));
  fs.chmodSync(path.join(bin, "bazel"), 0o755);
  for (const [tool, source] of [["mountpoint", "mountpoint.sh"], ["fuser", "fuser.js"], ["sudo", "sudo.sh"]]) {
    fs.copyFileSync(path.join(__dirname, "fixtures", source), path.join(bin, tool));
    fs.chmodSync(path.join(bin, tool), 0o755);
  }
  const log = path.join(root, "shutdown.log");
  const env = {
    ...process.env,
    GITHUB_WORKSPACE: root,
    BAZEL_SHUTDOWN_LOG: log,
    NODE_BINARY: process.execPath,
    HANGING_PID: path.join(root, "hanging.pid"),
    FUSER_LOG: path.join(root, "fuser.log"),
    CACHE_HOLDER: path.join(root, "holder"),
    PATH: `${bin}:${process.env.PATH}`,
  };
  delete env["INPUT_BAZEL-MODULES"];
  return {
    root,
    env,
    run(modules) {
      if (modules !== undefined) env["INPUT_BAZEL-MODULES"] = modules;
      return spawnSync(process.execPath, [path.join(__dirname, "post.js")], {
        env,
        encoding: "utf8",
        timeout: 10000,
        killSignal: "SIGKILL",
      });
    },
    // Modules shut down concurrently, so their order is unspecified.
    calls() {
      return fs.readFileSync(log, "utf8").trim().split("\n").sort();
    },
  };
}

test("shuts down every module and ignores blank lines and surrounding whitespace", (t) => {
  const f = fixture(t);
  fs.mkdirSync(path.join(f.root, "examples"));
  fs.mkdirSync(path.join(f.root, "tests"));
  const result = f.run(" .\r\n\n examples \r\ntests\n");
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(f.calls(), [
    f.root,
    path.join(f.root, "examples"),
    path.join(f.root, "tests"),
  ].sort());
});

test("also shuts down the add-on modules a build ran in", (t) => {
  const f = fixture(t);
  for (const built of ["addons/widget/examples", "addons/.selftest/examples", "addons/gadget"]) {
    fs.mkdirSync(path.join(f.root, built), { recursive: true });
    fs.symlinkSync(f.root, path.join(f.root, built, "bazel-out"));
  }
  fs.mkdirSync(path.join(f.root, "addons/unbuilt/examples"), { recursive: true });
  fs.writeFileSync(path.join(f.root, "addons/README.md"), "");
  assert.equal(f.run(".\naddons/gadget\n").status, 0);
  assert.deepEqual(f.calls(), [
    f.root,
    path.join(f.root, "addons/.selftest/examples"),
    path.join(f.root, "addons/gadget"),
    path.join(f.root, "addons/widget/examples"),
  ].sort());
});

test("also shuts down nested modules a build ran in, but not Bazel's own links", (t) => {
  const f = fixture(t);
  for (const built of ["rules_godot", "rules_godot/tests"]) {
    fs.mkdirSync(path.join(f.root, built), { recursive: true });
    fs.symlinkSync(f.root, path.join(f.root, built, "bazel-out"));
  }
  fs.mkdirSync(path.join(f.root, "rules_godot/bazel-bin/nested"), { recursive: true });
  fs.symlinkSync(f.root, path.join(f.root, "rules_godot/bazel-bin/nested/bazel-out"));
  fs.mkdirSync(path.join(f.root, "rules_godot/examples"));
  assert.equal(f.run().status, 0);
  assert.deepEqual(f.calls(), [
    f.root,
    path.join(f.root, "rules_godot"),
    path.join(f.root, "rules_godot/tests"),
  ].sort());
});

test("defaults to the root module", (t) => {
  const f = fixture(t);
  assert.equal(f.run().status, 0);
  assert.deepEqual(f.calls(), [f.root]);
});

test("warns on failure and still shuts down other modules", (t) => {
  const f = fixture(t);
  fs.mkdirSync(path.join(f.root, "failing"));
  const result = f.run("failing\n.");
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /::warning::bazel shutdown in failing failed: 23/);
  assert.deepEqual(f.calls(), [path.join(f.root, "failing"), f.root].sort());
});

test("warns about a missing module without preventing other cleanup", (t) => {
  const f = fixture(t);
  const result = f.run("missing\n.");
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /::warning::bazel shutdown in missing failed:/);
  assert.deepEqual(f.calls(), [f.root]);
});

test("bounds a hung shutdown even when SIGTERM is ignored and continues other modules", (t) => {
  const f = fixture(t);
  fs.mkdirSync(path.join(f.root, "hanging"));
  f.env["INPUT_SHUTDOWN-TIMEOUT-SECONDS"] = "1";
  const result = f.run("hanging\n.");
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /::warning::.*hanging.*timed out/);
  assert.match(result.stdout, /Bazel stopped in \.\n/);
  assert.deepEqual(f.calls(), [path.join(f.root, "hanging"), f.root].sort());
  const pid = Number(fs.readFileSync(f.env.HANGING_PID, "utf8"));
  assert.throws(() => process.kill(pid, 0), { code: "ESRCH" });
});

test("does not wait for a busy Bazel lock", (t) => {
  const f = fixture(t);
  fs.mkdirSync(path.join(f.root, "locked"));
  f.env["INPUT_SHUTDOWN-TIMEOUT-SECONDS"] = "1";
  const result = f.run("locked\n.");
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /::warning::bazel shutdown in locked failed: 9/);
  assert.doesNotMatch(result.stdout, /timed out/);
  assert.deepEqual(f.calls(), [path.join(f.root, "locked"), f.root].sort());
});

test("releases stubborn sticky-disk holders after module shutdown", (t) => {
  const f = fixture(t);
  f.env["INPUT_REPOSITORY-CACHE"] = path.join(f.root, "cache_mount");
  fs.mkdirSync(f.env["INPUT_REPOSITORY-CACHE"]);
  f.env.HOLDER_MODE = "stubborn";
  fs.writeFileSync(f.env.CACHE_HOLDER, "open repository cache file");
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.existsSync(f.env.CACHE_HOLDER), false);
  const calls = fs.readFileSync(f.env.FUSER_LOG, "utf8").trim().split("\n").map(JSON.parse);
  const kills = calls.filter((args) => args.includes("-k"));
  assert.equal(kills.length, 2);
  assert.ok(kills[0].includes("-TERM"));
  assert.ok(kills[1].includes("-KILL"));
  for (const args of calls) {
    assert.ok(args.includes("-M"), "Every filesystem-wide fuser call must require a mountpoint");
    assert.equal(args.at(-1), f.env["INPUT_REPOSITORY-CACHE"]);
  }
});

test("never signals filesystem holders when the cache path is not mounted", (t) => {
  const f = fixture(t);
  f.env["INPUT_REPOSITORY-CACHE"] = path.join(f.root, "ordinary_directory");
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /not a mountpoint/);
  assert.equal(fs.existsSync(f.env.FUSER_LOG), false);
});

test("Linux CI releases a real mounted filesystem held by a stubborn worker", {
  skip: process.platform !== "linux" || process.env.GITHUB_ACTIONS !== "true",
  timeout: 30000,
}, async (t) => {
  const { spawn, execFile } = require("node:child_process");
  const { once } = require("node:events");
  const execute = require("node:util").promisify(execFile);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "mounted-bazel-cleanup-"));
  const cache = path.join(root, "cache");
  fs.mkdirSync(cache);
  let mounted = false;
  let worker;
  let workerClosed;
  const sudo = (...args) => execute("sudo", ["-n", ...args], {
    encoding: "utf8", timeout: 5000, killSignal: "SIGKILL",
  });
  const waitForWorker = () => Promise.race([
    workerClosed,
    new Promise((_, reject) => {
      const timer = setTimeout(() => reject(new Error("Worker did not close after cleanup")), 5000);
      timer.unref();
    }),
  ]);
  t.after(async () => {
    try {
      if (worker) { worker.kill("SIGKILL"); await waitForWorker(); }
    } finally {
      if (mounted) await sudo("umount", "--", cache);
      fs.rmSync(root, { recursive: true, force: true });
    }
  });
  await sudo("mount", "-t", "tmpfs", "-o", "size=8m", "tmpfs", cache);
  mounted = true;
  worker = spawn(process.execPath, ["-e", `
    require("node:fs").openSync("worker-input", "w");
    process.on("SIGTERM", () => {});
    process.send("ready");
    setInterval(() => {}, 1000);
  `], { cwd: cache, stdio: ["ignore", "ignore", "ignore", "ipc"] });
  workerClosed = once(worker, "close");
  await once(worker, "message", { signal: AbortSignal.timeout(5000) });
  // Drain the worker's IPC/exit events while cleanup signals it, with explicit
  // deadlines so a live worker produces a failure instead of hanging the job.
  const result = await execute(process.execPath, [path.join(__dirname, "post.js")], {
    env: {
      ...process.env,
      GITHUB_WORKSPACE: root,
      // An intentionally blank module list leaves real checkout daemons alone;
      // this test owns only the mounted worker.
      "INPUT_BAZEL-MODULES": " ",
      "INPUT_REPOSITORY-CACHE": cache,
    },
    encoding: "utf8", timeout: 15000, killSignal: "SIGKILL",
  });
  t.diagnostic(result.stdout);
  assert.match(result.stdout, /Repository cache released:/);
  await waitForWorker();
  await sudo("umount", "--", cache);
  mounted = false;
});

test("refuses a symlink to the root filesystem before signaling holders", (t) => {
  const f = fixture(t);
  const cache = path.join(f.root, "cache_mount");
  fs.symlinkSync(path.parse(f.root).root, cache, "dir");
  f.env["INPUT_REPOSITORY-CACHE"] = cache;
  const result = f.run();
  assert.equal(result.status, 1);
  assert.match(result.stdout, /Refusing to clean filesystem root/);
  assert.equal(fs.existsSync(f.env.FUSER_LOG), false);
});
