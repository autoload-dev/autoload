// EXPERIMENT(web-browser): reports a Godot web export's log and exit code to the harness
// server, without the DevTools protocol. The server inserts this script right after the
// page's `<script src="index.js">`, so `Engine` exists and the page's own inline script has
// not yet run. The exported files stay unchanged; only the served page is rewritten.
(function () {
	'use strict';
	const harness = window.__HARNESS__ || {};
	let load = 1;
	try {
		load = Number(sessionStorage.getItem('__harness_load') || '0') + 1;
		sessionStorage.setItem('__harness_load', String(load));
	} catch (e) { /* no storage: count stays 1 */ }
	let seq = 0;

	// One request in flight at a time, carrying every event queued meanwhile: a burst of
	// prints must not open a connection each (the server's listen backlog drops them).
	const queue = [];
	let inFlight = false;
	function flush() {
		if (inFlight || queue.length === 0) {
			return;
		}
		inFlight = true;
		const batch = queue.splice(0, queue.length);
		fetch('/__harness/event', { method: 'POST', body: JSON.stringify(batch) })
			.catch(function () { /* the server is gone */ })
			.finally(function () {
				inFlight = false;
				flush();
			});
	}
	function send(kind, data) {
		queue.push(Object.assign({ load: load, seq: seq++, t: performance.now(), kind: kind }, data));
		flush();
	}

	function webglRenderer() {
		try {
			const gl = document.createElement('canvas').getContext('webgl2');
			if (!gl) {
				return null;
			}
			const ext = gl.getExtension('WEBGL_debug_renderer_info');
			const name = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
			const lose = gl.getExtension('WEBGL_lose_context');
			if (lose) {
				lose.loseContext();
			}
			return name;
		} catch (e) {
			return 'error: ' + e;
		}
	}

	send('boot', {
		webgl2: webglRenderer(),
		crossOriginIsolated: window.crossOriginIsolated === true,
		sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
		serviceWorkerController: !!(navigator.serviceWorker && navigator.serviceWorker.controller),
		userAgent: navigator.userAgent,
	});

	window.addEventListener('error', function (e) {
		send('page-error', { text: String(e.message || e) });
	});
	window.addEventListener('unhandledrejection', function (e) {
		send('page-error', { text: 'unhandled rejection: ' + String(e.reason && (e.reason.stack || e.reason)) });
	});
	const consoleError = console.error.bind(console);
	console.error = function () {
		send('console-error', { text: Array.prototype.map.call(arguments, String).join(' ') });
		consoleError.apply(null, arguments);
	};
	// What a user sees: the page's status notice, e.g. "The following features ... are missing".
	document.addEventListener('DOMContentLoaded', function () {
		const notice = document.getElementById('status-notice');
		if (!notice) {
			return;
		}
		new MutationObserver(function () {
			send('notice', { text: notice.innerText });
		}).observe(notice, { childList: true, subtree: true });
	});

	// Godot's page reloads as soon as the service worker is registered, which can be before it
	// activates; the reloaded page is then not controlled, still not isolated, and stops with
	// "Service worker already exists". Opt-in: wait until the worker is active, then reload.
	if (harness.swReload && !window.crossOriginIsolated && 'serviceWorker' in navigator
		&& !navigator.serviceWorker.controller && load >= 2 && load < 5) {
		navigator.serviceWorker.ready.then(function () {
			send('sw-ready-reload', {});
			setTimeout(function () {
				location.reload();
			}, 50);
		});
	}

	if (typeof Engine === 'undefined') {
		send('page-error', { text: 'Engine is not defined' });
		return;
	}
	const missing = Engine.getMissingFeatures({ threads: harness.threads === true });
	send('features', { missing: missing });

	// The page's `new Engine(GODOT_CONFIG)` becomes `new Engine(window.__harnessConfig(GODOT_CONFIG))`:
	// `Engine` is a script-scoped `const` with a fresh prototype per instance, so neither
	// the binding nor `startGame` can be replaced from outside.
	window.__harnessConfig = function (config) {
		const hooks = {
			onPrint: function () {
				send('stdout', { text: Array.prototype.join.call(arguments, ' ') });
			},
			onPrintError: function () {
				send('stderr', { text: Array.prototype.join.call(arguments, ' ') });
			},
			onExit: function (code) {
				send('exit', { code: code });
			},
		};
		if (Array.isArray(harness.args)) {
			hooks.args = harness.args;
		}
		send('start', { args: hooks.args || config.args || [] });
		return Object.assign({}, config, hooks);
	};
}());
