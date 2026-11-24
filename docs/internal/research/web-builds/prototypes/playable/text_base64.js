// The payload as base64: 4 characters per 3 bytes, accepted everywhere.
function decodeText(text, size) {
	const binary = atob(text);
	const out = new Uint8Array(size);
	for (let i = 0; i < size; i++) {
		out[i] = binary.charCodeAt(i);
	}
	return out;
}
