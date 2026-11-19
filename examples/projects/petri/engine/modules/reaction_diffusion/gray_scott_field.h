#pragma once

#include "core/io/image.h"
#include "core/object/ref_counted.h"
#include "core/templates/local_vector.h"

// A Gray-Scott reaction-diffusion field on the CPU: two chemicals A and B per cell, stepped
// with a 3x3 Laplacian on a wrap-around grid. Deterministic for one seed, so it runs headless
// and on the Compatibility renderer alike; get_image() paints B's concentration with a fixed
// palette so a script only updates a texture.
class GrayScottField : public RefCounted {
	GDCLASS(GrayScottField, RefCounted);

	int width = 0;
	int height = 0;
	uint64_t rng_state = 0;
	float feed = 0.055f;
	float kill = 0.062f;
	LocalVector<float> a;
	LocalVector<float> b;
	LocalVector<float> next_a;
	LocalVector<float> next_b;
	Ref<Image> image;

	float _next_random();
	static const uint8_t *_palette();

protected:
	static void _bind_methods();

public:
	void setup(int p_width, int p_height, int p_seed);
	void clear();
	void set_rates(float p_feed, float p_kill);
	float get_feed() const { return feed; }
	float get_kill() const { return kill; }
	int get_width() const { return width; }
	int get_height() const { return height; }
	void seed_disc(const Vector2 &p_center, float p_radius);
	void step(int p_count = 1);
	float get_value(int p_x, int p_y) const;
	int64_t checksum() const;
	Ref<Image> get_image();
};
