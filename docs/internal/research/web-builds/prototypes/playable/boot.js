// Starts the Godot web export embedded in this page: decodes and unpacks the payload,
// runs the engine's loader, and answers the loader's requests from memory.
// The packer defines PAYLOAD = { files: [[name, size], ...], packed, total } and decodeText.
(function () {
	function unpack() {
		const text = document.getElementById('payload').textContent;
		const all = lzmaDecode(decodeText(text, PAYLOAD.packed), PAYLOAD.total);
		const files = {};
		let at = 0;
		for (const [name, size] of PAYLOAD.files) {
			files[name] = all.subarray(at, at + size);
			at += size;
		}
		return files;
	}

	function serve(files) {
		const fetchUrl = window.fetch.bind(window);
		window.fetch = function (url, init) {
			const file = files[String(url).split('/').pop()];
			if (!file) {
				return fetchUrl(url, init);
			}
			const type = String(url).endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream';
			return Promise.resolve(new Response(file, { headers: { 'Content-Type': type, 'Content-Length': String(file.length) } }));
		};
	}

	const files = unpack();
	const loader = document.createElement('script');
	loader.textContent = new TextDecoder().decode(files['index.js']);
	document.head.appendChild(loader);
	serve(files);
	const engine = new Engine({
		args: [],
		canvas: document.getElementById('canvas'),
		canvasResizePolicy: 2,
		executable: 'index',
		focusCanvas: true,
	});
	engine.startGame().catch(function (err) {
		console.error(err);
	});
})();
