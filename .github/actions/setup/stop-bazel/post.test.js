const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");

function alive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    throw error;
  }
}

function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "bazel-cleanup-")));
  const pids = [];
  t.after(() => {
    const pidFile = path.join(root, "hanging.pid");
    if (fs.existsSync(pidFile)) pids.push(Number(fs.readFileSync(pidFile, "utf8")));
    for (const pid of pids) if (alive(pid)) process.kill(pid, "SIGKILL");
    fs.rmSync(root, { recursive: true, force: true });
  });
  const bin = path.join(root, "bin");
  fs.mkdirSync(bin);
  for (const [tool, source] of [["bazel", "bazel.sh"], ["mountpoint", "mountpoint.sh"], ["fuser", "fuser.js"], ["sudo", "sudo.sh"]]) {
    fs.copyFileSync(path.join(__dirname, "fixtures", source), path.join(bin, tool));
    fs.chmodSync(path.join(bin, tool), 0o755);
  }
  const log = path.join(root, "shutdown.log");
  const env = {
    ...process.env,
    GITHUB_WORKSPACE: root,
    XDG_CACHE_HOME: path.join(root, "cache"),
    USER: "tester",
    RUNNER_OS: "Linux",
    BAZEL_SHUTDOWN_LOG: log,
    NODE_BINARY: process.execPath,
    HANGING_PID: path.join(root, "hanging.pid"),
    FUSER_LOG: path.join(root, "fuser.log"),
    CACHE_HOLDER: path.join(root, "holder"),
    PATH: `${bin}:${process.env.PATH}`,
  };
  delete env.PERSISTENT_RUNNER;
  const userRoot = path.join(root, "cache/bazel/_bazel_tester");
  return {
    root,
    env,
    userRoot,
    // Starts a fake server for an output base, detached so that it outlives its starter like
    // a real one. Bazel records the workspace in the output base's DO_NOT_BUILD_HERE file.
    server(outputBase, { workspace, mode = "graceful" } = {}) {
      if (workspace) {
        fs.mkdirSync(path.dirname(path.join(outputBase, "DO_NOT_BUILD_HERE")), { recursive: true });
        fs.writeFileSync(path.join(outputBase, "DO_NOT_BUILD_HERE"), workspace);
      }
      spawnSync("sh", ["-c", '"$@" >/dev/null 2>&1 &', "sh",
        process.execPath, path.join(__dirname, "fixtures/server.js"), `--output_base=${outputBase}`, mode]);
      const pidFile = path.join(outputBase, "server/server.pid.txt");
      const deadline = Date.now() + 5000;
      while (!fs.existsSync(pidFile) || !fs.readFileSync(pidFile, "utf8")) {
        if (Date.now() > deadline) throw new Error(`Fake server did not start: ${outputBase}`);
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 20);
      }
      const pid = Number(fs.readFileSync(pidFile, "utf8"));
      pids.push(pid);
      return pid;
    },
    workspace(name) {
      const workspace = path.join(root, name);
      fs.mkdirSync(workspace, { recursive: true });
      return workspace;
    },
    run(overrides = {}) {
      return spawnSync(process.execPath, [path.join(__dirname, "post.js")], {
        env: { ...env, ...overrides },
        encoding: "utf8",
        timeout: 20000,
        killSignal: "SIGKILL",
      });
    },
    // Servers shut down concurrently, so their order is unspecified.
    calls() {
      if (!fs.existsSync(log)) return [];
      return fs.readFileSync(log, "utf8").trim().split("\n").sort();
    },
  };
}

test("shuts down every server under the output user root, in its workspace", (t) => {
  const f = fixture(t);
  const one = f.workspace("one");
  const two = f.workspace("nested/two");
  const first = f.server(path.join(f.userRoot, "aaa"), { workspace: one });
  const second = f.server(path.join(f.userRoot, "bbb"), { workspace: two });
  fs.mkdirSync(path.join(f.userRoot, "install/0123"), { recursive: true });
  fs.writeFileSync(path.join(f.userRoot, "install/0123/DO_NOT_BUILD_HERE"), one);
  fs.mkdirSync(path.join(f.userRoot, "unstarted"));
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Found 2 Bazel server\(s\)/);
  assert.deepEqual(f.calls(), [
    `${one} ${path.join(f.userRoot, "aaa")}`,
    `${two} ${path.join(f.userRoot, "bbb")}`,
  ].sort());
  assert.equal(alive(first), false);
  assert.equal(alive(second), false);
});

test("leaves every server and the cache alone on a persistent or non-Linux runner", (t) => {
  const f = fixture(t);
  const pid = f.server(path.join(f.userRoot, "aaa"), { workspace: f.workspace("one") });
  f.env["INPUT_REPOSITORY-CACHE"] = path.join(f.root, "cache_mount");
  fs.mkdirSync(f.env["INPUT_REPOSITORY-CACHE"]);
  fs.writeFileSync(f.env.CACHE_HOLDER, "open repository cache file");
  for (const runner of [{ PERSISTENT_RUNNER: "true" }, { RUNNER_OS: "macOS" }, { RUNNER_OS: "" }]) {
    const result = f.run(runner);
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /leaving Bazel servers running/);
  }
  assert.deepEqual(f.calls(), []);
  assert.equal(alive(pid), true);
  assert.equal(fs.existsSync(f.env.FUSER_LOG), false);
});

test("leaves a stale PID alone when its process is no server of that output base", (t) => {
  const f = fixture(t);
  const pid = f.server(path.join(f.root, "elsewhere"));
  const recycled = path.join(f.userRoot, "recycled/server");
  fs.mkdirSync(recycled, { recursive: true });
  fs.writeFileSync(path.join(recycled, "server.pid.txt"), String(pid));
  fs.writeFileSync(path.join(f.userRoot, "recycled/DO_NOT_BUILD_HERE"), f.workspace("one"));
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(f.calls(), []);
  assert.equal(alive(pid), true);
});

test("stops a server whose shutdown fails and still shuts down other servers", (t) => {
  const f = fixture(t);
  const failing = f.workspace("failing");
  const one = f.workspace("one");
  const pids = [
    f.server(path.join(f.userRoot, "aaa"), { workspace: failing }),
    f.server(path.join(f.userRoot, "bbb"), { workspace: one }),
  ];
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /::warning::bazel shutdown of .*failing failed: 23/);
  assert.match(result.stdout, /Sending SIGTERM to Bazel server/);
  assert.deepEqual(f.calls(), [
    `${failing} ${path.join(f.userRoot, "aaa")}`,
    `${one} ${path.join(f.userRoot, "bbb")}`,
  ].sort());
  for (const pid of pids) assert.equal(alive(pid), false);
});

test("kills a server that ignores SIGTERM and whose workspace is gone", (t) => {
  const f = fixture(t);
  const pid = f.server(path.join(f.userRoot, "aaa"), { workspace: path.join(f.root, "deleted"), mode: "stubborn" });
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /::warning::workspace of Bazel server aaa is gone/);
  assert.match(result.stdout, /Sending SIGKILL to Bazel server/);
  assert.deepEqual(f.calls(), []);
  assert.equal(alive(pid), false);
});

test("bounds a hung shutdown even when SIGTERM is ignored and continues other servers", (t) => {
  const f = fixture(t);
  const hanging = f.workspace("hanging");
  const one = f.workspace("one");
  const pids = [
    f.server(path.join(f.userRoot, "aaa"), { workspace: hanging }),
    f.server(path.join(f.userRoot, "bbb"), { workspace: one }),
  ];
  f.env["INPUT_SHUTDOWN-TIMEOUT-SECONDS"] = "1";
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /::warning::.*hanging.*timed out/);
  assert.match(result.stdout, new RegExp(`Bazel stopped: ${path.join(f.userRoot, "bbb")}\n`));
  assert.equal(f.calls().length, 2);
  for (const pid of pids) assert.equal(alive(pid), false);
  assert.equal(alive(Number(fs.readFileSync(f.env.HANGING_PID, "utf8"))), false);
});

test("does not wait for a busy Bazel lock", (t) => {
  const f = fixture(t);
  const pid = f.server(path.join(f.userRoot, "aaa"), { workspace: f.workspace("locked") });
  f.env["INPUT_SHUTDOWN-TIMEOUT-SECONDS"] = "1";
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /::warning::bazel shutdown of .*locked failed: 9/);
  assert.doesNotMatch(result.stdout, /timed out/);
  assert.equal(alive(pid), false);
});

test("releases stubborn sticky-disk holders after server shutdown", (t) => {
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
      // An empty output user root leaves the runner's real Bazel servers alone;
      // this test owns only the mounted worker.
      XDG_CACHE_HOME: root,
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
