// LZMA decoder for the `.lzma` ("alone") format, after Igor Pavlov's public-domain
// LzmaSpec.cpp. The whole output stays in memory and is its own dictionary.
// lzmaDecode(source: Uint8Array, size: number) -> Uint8Array of `size` bytes.
function lzmaDecode(src, size) {
	let props = src[0];
	const lc = props % 9;
	props = (props / 9) | 0;
	const lp = props % 5;
	const pb = (props / 5) | 0;
	const out = new Uint8Array(size);
	let pos = 14;
	let range = 0xffffffff;
	let code = 0;
	for (let i = 0; i < 4; i++) {
		code = code * 256 + src[pos++];
	}

	const probs = (n) => new Uint16Array(n).fill(1024);
	function bit(p, i) {
		const v = p[i];
		const bound = (range >>> 11) * v;
		let b = 0;
		if (code < bound) {
			range = bound;
			p[i] = v + ((2048 - v) >> 5);
		} else {
			range -= bound;
			code -= bound;
			p[i] = v - (v >> 5);
			b = 1;
		}
		if (range < 16777216) {
			range *= 256;
			code = code * 256 + src[pos++];
		}
		return b;
	}
	function direct(n) {
		let r = 0;
		while (n--) {
			range = range >>> 1;
			r <<= 1;
			if (code >= range) {
				code -= range;
				r |= 1;
			}
			if (range < 16777216) {
				range *= 256;
				code = code * 256 + src[pos++];
			}
		}
		return r >>> 0;
	}
	function tree(p, base, bits) {
		let m = 1;
		for (let i = 0; i < bits; i++) {
			m = (m << 1) + bit(p, base + m);
		}
		return m - (1 << bits);
	}
	function reverse(p, base, bits) {
		let m = 1;
		let s = 0;
		for (let i = 0; i < bits; i++) {
			const b = bit(p, base + m);
			m = (m << 1) + b;
			s |= b << i;
		}
		return s;
	}
	function lengths() {
		const l = { c: probs(2), low: probs(16 << 3), mid: probs(16 << 3), high: probs(256) };
		l.get = (ps) => {
			if (!bit(l.c, 0)) {
				return tree(l.low, ps << 3, 3);
			}
			if (!bit(l.c, 1)) {
				return 8 + tree(l.mid, ps << 3, 3);
			}
			return 16 + tree(l.high, 0, 8);
		};
		return l;
	}

	const isMatch = probs(192);
	const isRep = probs(12);
	const isRepG0 = probs(12);
	const isRepG1 = probs(12);
	const isRepG2 = probs(12);
	const isRep0Long = probs(192);
	const literal = probs(0x300 << (lc + lp));
	const posSlot = probs(256);
	const posSpec = probs(115);
	const align = probs(16);
	const matchLen = lengths();
	const repLen = lengths();
	const pbMask = (1 << pb) - 1;
	const lpMask = (1 << lp) - 1;
	let state = 0;
	let rep0 = 0;
	let rep1 = 0;
	let rep2 = 0;
	let rep3 = 0;
	let n = 0;

	function distance(len) {
		const slot = tree(posSlot, (len < 3 ? len : 3) << 6, 6);
		if (slot < 4) {
			return slot;
		}
		const bits = (slot >> 1) - 1;
		let d = (2 | (slot & 1)) * 2 ** bits;
		if (slot < 14) {
			return d + reverse(posSpec, d - slot, bits);
		}
		d += direct(bits - 4) * 16;
		return d + reverse(align, 0, 4);
	}
	function decodeLiteral() {
		const prev = n > 0 ? out[n - 1] : 0;
		const base = 0x300 * (((n & lpMask) << lc) + (prev >> (8 - lc)));
		let s = 1;
		if (state >= 7) {
			let match = out[n - rep0 - 1];
			do {
				const mb = (match >> 7) & 1;
				match <<= 1;
				const b = bit(literal, base + ((1 + mb) << 8) + s);
				s = (s << 1) | b;
				if (mb !== b) {
					break;
				}
			} while (s < 0x100);
		}
		while (s < 0x100) {
			s = (s << 1) | bit(literal, base + s);
		}
		out[n++] = s & 0xff;
		state = state < 4 ? 0 : state < 10 ? state - 3 : state - 6;
	}
	function rep(ps) {
		if (!bit(isRepG0, state)) {
			if (!bit(isRep0Long, (state << 4) + ps)) {
				state = state < 7 ? 9 : 11;
				out[n] = out[n - rep0 - 1];
				n++;
				return 0;
			}
		} else {
			let d;
			if (!bit(isRepG1, state)) {
				d = rep1;
			} else {
				if (!bit(isRepG2, state)) {
					d = rep2;
				} else {
					d = rep3;
					rep3 = rep2;
				}
				rep2 = rep1;
			}
			rep1 = rep0;
			rep0 = d;
		}
		state = state < 7 ? 8 : 11;
		return repLen.get(ps) + 2;
	}
	function match(ps) {
		rep3 = rep2;
		rep2 = rep1;
		rep1 = rep0;
		const len = matchLen.get(ps);
		state = state < 7 ? 7 : 10;
		rep0 = distance(len);
		return len + 2;
	}

	while (n < size) {
		const ps = n & pbMask;
		if (!bit(isMatch, (state << 4) + ps)) {
			decodeLiteral();
			continue;
		}
		let len = bit(isRep, state) ? rep(ps) : match(ps);
		if (rep0 === 0xffffffff || rep0 >= n) {
			break; // End marker, or corrupt data.
		}
		while (len-- > 0 && n < size) {
			out[n] = out[n - rep0 - 1];
			n++;
		}
	}
	if (n !== size) {
		throw new Error(`LZMA: ${n} of ${size} bytes`);
	}
	return out;
}
