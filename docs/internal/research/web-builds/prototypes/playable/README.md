# One HTML file for playable ads

`pack_playable.py` packs a Godot web export (`index.wasm`, `index.js`, `index.pck`) into
a single `index.html` that makes no request. Throwaway research tooling; not part of the
ruleset.

```sh
python3 pack_playable.py <web export dir> index.html [--encoding base64|seven]
```

## What the networks count

From `../../research_notes/Web Builds Entscheidungsgrundlagen/playable_ads.md` (sources
from 2026-09 and -10): almost every network allows 5 MB, and they count it in one of two
ways.

| Counted size | Networks | Encoding they accept |
| --- | --- | --- |
| the raw HTML | AppLovin, Unity Ads, Moloco, Meta single HTML (2 MB) | base64; AppLovin also base122 |
| the ZIP | Google Ads, TikTok/Pangle, Mintegral, Snapchat, Meta ZIP | base64 inside, which deflate mostly takes back |

So the payload must be as small as possible after compression, and its decoder counts
too. Browsers decompress only gzip and deflate natively (`DecompressionStream`); a native
Brotli decoder ships in Firefox only, so anything stronger needs its own decoder.

## The choice: LZMA, decoded by 3.7 KB of JS

Lichtpost R17 with lossy backgrounds and stripped bytecode, all three files
(5,402,706 B):

| Compression | payload | decoder |
| --- | ---: | --- |
| deflate -9 | 2,275,656 B | native |
| zstd -19 (`--long` gains nothing) | 1,933,055 B | `fzstd`, 8 KB |
| Brotli 11, 16 MB window | 1,851,029 B | 66 to 151 KB of JS (static dictionary) |
| **LZMA** (`.lzma`, preset 9e) | **1,823,451 B** | `lzma.js`, written here, 3.7 KB as embedded |

`lzma.js` follows the public-domain reference decoder (LzmaSpec.cpp); the output is its
own dictionary. It decodes the 5.4 MB in about 200 ms on an M-series Mac, in Node and in
Chrome; a slow Android phone will take several times that.

`boot.js` decodes the payload, runs the engine's loader from it as an inline script, and
replaces `fetch()` so the loader's requests for `index.wasm` and `index.pck` are answered
from memory. The engine itself is unchanged. The audio worklets stay out: the build without
threads never loads them.

## Encodings

- `base64`: 4 characters per 3 bytes, accepted everywhere.
- `seven`: 7 bits per byte of the page, like base122. The seven values HTML or JS could
  mangle (NUL, LF, CR, `"`, `&`, `<`, `\`) become one 2-byte UTF-8 character that also
  carries the next 7 bits, so the ratio stays 8/7. Without `<` the payload cannot close its
  script element. Only for AppLovin, the one network that allows base122.

## Result

| Lichtpost R17 | HTML | in a ZIP |
| --- | ---: | ---: |
| files embedded uncompressed as base64 (before) | 7,160,250 B | not measured |
| **LZMA + base64** | **2,436,840 B** | **1,844,351 B** |
| LZMA + seven | 2,089,811 B | 1,915,094 B |

The base64 file fits every 5 MB network with 2.5 MB to spare, counted raw or zipped; the
7-bit file gives AppLovin 2.9 MB of room. Meta's 2 MB single HTML stays out of reach
(Meta's ZIP format allows 5 MB). Both play in Chrome with no request but the page.

Not done here: the networks' CTA and lifecycle calls (MRAID, `FbPlayableAd`,
`ExitApi`), a loading screen, and a check of start-up time on a slow phone.
