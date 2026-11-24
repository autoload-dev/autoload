// The payload as 7-bit text (in the spirit of base122): each character carries 7 bits.
// The seven values HTML or JS might mangle are written as one 2-byte UTF-8 character
// U+0100 + index * 128 + next 7 bits, so every byte of the page carries 7 bits.
function decodeText(text, size) {
	const illegal = [0, 10, 13, 34, 38, 60, 92];
	const out = new Uint8Array(size);
	let acc = 0;
	let bits = 0;
	let n = 0;
	function push(v) {
		acc = (acc << 7) | v;
		bits += 7;
		if (bits >= 8) {
			bits -= 8;
			out[n++] = acc >> bits;
			acc &= (1 << bits) - 1;
		}
	}
	for (let i = 0; i < text.length && n < size; i++) {
		const c = text.charCodeAt(i);
		if (c < 128) {
			push(c);
		} else {
			push(illegal[(c - 256) >> 7]);
			push((c - 256) & 127);
		}
	}
	return out;
}
