#include "gray_scott_field.h"

#include "core/math/math_funcs.h"
#include "core/object/class_db.h"

#include <cstring>

namespace {

constexpr float DIFFUSE_A = 1.0f;
constexpr float DIFFUSE_B = 0.5f;
// B rarely exceeds this concentration; the palette spans up to here.
constexpr float PALETTE_RANGE = 0.345f;

struct PaletteStop {
	float at;
	uint8_t rgb[3];
};

// Dish floor, deep teal, bright teal, amber.
constexpr PaletteStop PALETTE_STOPS[] = {
	{ 0.00f, { 6, 20, 27 } },
	{ 0.18f, { 10, 48, 56 } },
	{ 0.45f, { 20, 120, 112 } },
	{ 0.72f, { 92, 200, 176 } },
	{ 1.00f, { 243, 213, 138 } },
};

} // namespace

const uint8_t *GrayScottField::_palette() {
	static uint8_t table[256 * 3];
	static bool ready = false;
	if (!ready) {
		constexpr int stops = sizeof(PALETTE_STOPS) / sizeof(PALETTE_STOPS[0]);
		for (int i = 0; i < 256; i++) {
			const float t = i / 255.0f;
			int s = 0;
			while (s < stops - 2 && t > PALETTE_STOPS[s + 1].at) {
				s++;
			}
			const PaletteStop &from = PALETTE_STOPS[s];
			const PaletteStop &to = PALETTE_STOPS[s + 1];
			const float u = (t - from.at) / (to.at - from.at);
			for (int c = 0; c < 3; c++) {
				table[i * 3 + c] = uint8_t(from.rgb[c] + (to.rgb[c] - from.rgb[c]) * u);
			}
		}
		ready = true;
	}
	return table;
}

float GrayScottField::_next_random() {
	// A 64-bit linear congruential generator; only the high bits are used.
	rng_state = rng_state * 6364136223846793005ULL + 1442695040888963407ULL;
	return float(rng_state >> 40) / float(1 << 24);
}

void GrayScottField::setup(int p_width, int p_height, int p_seed) {
	ERR_FAIL_COND_MSG(p_width < 3 || p_height < 3, "A field needs at least 3x3 cells.");
	width = p_width;
	height = p_height;
	rng_state = uint64_t(p_seed);
	const uint32_t cells = uint32_t(width) * uint32_t(height);
	a.resize(cells);
	b.resize(cells);
	next_a.resize(cells);
	next_b.resize(cells);
	image.unref();
	clear();
}

void GrayScottField::clear() {
	for (uint32_t i = 0; i < a.size(); i++) {
		a[i] = 1.0f;
		b[i] = 0.0f;
	}
}

void GrayScottField::set_rates(float p_feed, float p_kill) {
	feed = p_feed;
	kill = p_kill;
}

void GrayScottField::seed_disc(const Vector2 &p_center, float p_radius) {
	ERR_FAIL_COND_MSG(width == 0, "Call setup() before seeding.");
	const float radius_squared = p_radius * p_radius;
	const int x0 = MAX(0, int(Math::floor(p_center.x - p_radius)));
	const int x1 = MIN(width - 1, int(Math::ceil(p_center.x + p_radius)));
	const int y0 = MAX(0, int(Math::floor(p_center.y - p_radius)));
	const int y1 = MIN(height - 1, int(Math::ceil(p_center.y + p_radius)));
	for (int y = y0; y <= y1; y++) {
		for (int x = x0; x <= x1; x++) {
			const float dx = x - p_center.x;
			const float dy = y - p_center.y;
			if (dx * dx + dy * dy > radius_squared) {
				continue;
			}
			const uint32_t i = uint32_t(y) * uint32_t(width) + uint32_t(x);
			b[i] = 0.9f + 0.1f * _next_random();
			a[i] = 0.5f;
		}
	}
}

void GrayScottField::step(int p_count) {
	ERR_FAIL_COND_MSG(width == 0, "Call setup() before stepping.");
	for (int n = 0; n < p_count; n++) {
		// Raw pointers: LocalVector's indexing checks bounds on every access, and the
		// stencil reads twenty cells per cell.
		const float *ca = a.ptr();
		const float *cb = b.ptr();
		float *na = next_a.ptr();
		float *nb = next_b.ptr();
		for (int y = 0; y < height; y++) {
			const uint32_t up = uint32_t(y == 0 ? height - 1 : y - 1) * uint32_t(width);
			const uint32_t down = uint32_t(y == height - 1 ? 0 : y + 1) * uint32_t(width);
			const uint32_t row = uint32_t(y) * uint32_t(width);
			for (int x = 0; x < width; x++) {
				const uint32_t left = uint32_t(x == 0 ? width - 1 : x - 1);
				const uint32_t right = uint32_t(x == width - 1 ? 0 : x + 1);
				const uint32_t i = row + uint32_t(x);
				const float va = ca[i];
				const float vb = cb[i];
				const float laplace_a = 0.2f * (ca[row + left] + ca[row + right] + ca[up + x] + ca[down + x]) +
						0.05f * (ca[up + left] + ca[up + right] + ca[down + left] + ca[down + right]) - va;
				const float laplace_b = 0.2f * (cb[row + left] + cb[row + right] + cb[up + x] + cb[down + x]) +
						0.05f * (cb[up + left] + cb[up + right] + cb[down + left] + cb[down + right]) - vb;
				const float reaction = va * vb * vb;
				na[i] = CLAMP(va + (DIFFUSE_A * laplace_a - reaction + feed * (1.0f - va)), 0.0f, 1.0f);
				nb[i] = CLAMP(vb + (DIFFUSE_B * laplace_b + reaction - (kill + feed) * vb), 0.0f, 1.0f);
			}
		}
		SWAP(a, next_a);
		SWAP(b, next_b);
	}
}

float GrayScottField::get_value(int p_x, int p_y) const {
	ERR_FAIL_INDEX_V(p_x, width, 0.0f);
	ERR_FAIL_INDEX_V(p_y, height, 0.0f);
	return b[uint32_t(p_y) * uint32_t(width) + uint32_t(p_x)];
}

int64_t GrayScottField::checksum() const {
	// FNV-1a over the bit patterns of both chemicals.
	uint64_t hash = 14695981039346656037ULL;
	for (uint32_t i = 0; i < a.size(); i++) {
		uint32_t bits_a;
		uint32_t bits_b;
		memcpy(&bits_a, &a[i], sizeof(bits_a));
		memcpy(&bits_b, &b[i], sizeof(bits_b));
		hash = (hash ^ bits_a) * 1099511628211ULL;
		hash = (hash ^ bits_b) * 1099511628211ULL;
	}
	return int64_t(hash);
}

Ref<Image> GrayScottField::get_image() {
	ERR_FAIL_COND_V_MSG(width == 0, Ref<Image>(), "Call setup() before reading the image.");
	if (image.is_null()) {
		image = Image::create_empty(width, height, false, Image::FORMAT_RGBA8);
	}
	// Painted in place: the image owns the only copy of its pixels, and ImageTexture's
	// update() copies them to the GPU without keeping a reference.
	const uint8_t *palette = _palette();
	const float *cb = b.ptr();
	uint8_t *out = image->ptrw();
	constexpr float scale = 255.0f / PALETTE_RANGE;
	for (uint32_t i = 0; i < b.size(); i++) {
		const int index = int(MIN(cb[i] * scale, 255.0f));
		const uint8_t *rgb = palette + index * 3;
		out[i * 4] = rgb[0];
		out[i * 4 + 1] = rgb[1];
		out[i * 4 + 2] = rgb[2];
		out[i * 4 + 3] = 255;
	}
	return image;
}

void GrayScottField::_bind_methods() {
	ClassDB::bind_method(D_METHOD("setup", "width", "height", "seed"), &GrayScottField::setup);
	ClassDB::bind_method(D_METHOD("clear"), &GrayScottField::clear);
	ClassDB::bind_method(D_METHOD("set_rates", "feed", "kill"), &GrayScottField::set_rates);
	ClassDB::bind_method(D_METHOD("get_feed"), &GrayScottField::get_feed);
	ClassDB::bind_method(D_METHOD("get_kill"), &GrayScottField::get_kill);
	ClassDB::bind_method(D_METHOD("get_width"), &GrayScottField::get_width);
	ClassDB::bind_method(D_METHOD("get_height"), &GrayScottField::get_height);
	ClassDB::bind_method(D_METHOD("seed_disc", "center", "radius"), &GrayScottField::seed_disc);
	ClassDB::bind_method(D_METHOD("step", "count"), &GrayScottField::step, DEFVAL(1));
	ClassDB::bind_method(D_METHOD("get_value", "x", "y"), &GrayScottField::get_value);
	ClassDB::bind_method(D_METHOD("checksum"), &GrayScottField::checksum);
	ClassDB::bind_method(D_METHOD("get_image"), &GrayScottField::get_image);
}
