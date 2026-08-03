shader_type canvas_item;

// Hub atmosphere — ink/teal depth, no purple.
uniform float u_time = 0.0;
uniform float u_calm = 0.4;
uniform float u_focus = 0.4;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = hash(i);
	float b = hash(i + vec2(1.0, 0.0));
	float c = hash(i + vec2(0.0, 1.0));
	float d = hash(i + vec2(1.0, 1.0));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
	float v = 0.0;
	float a = 0.5;
	for (int i = 0; i < 4; i++) {
		v += a * noise(p);
		p *= 2.05;
		a *= 0.5;
	}
	return v;
}

void fragment() {
	vec2 uv = UV;
	float t = u_time * 0.06;
	float n = fbm(uv * vec2(1.6, 1.1) + vec2(t * 0.4, -t * 0.25));
	float mist = fbm(uv * 3.0 + vec2(-t, t * 0.7));

	vec3 deep = vec3(0.02, 0.05, 0.07);
	vec3 mid = vec3(0.05, 0.14, 0.18);
	vec3 lift = vec3(0.12, 0.28, 0.30);
	vec3 warm = vec3(0.28, 0.18, 0.08);

	vec3 col = mix(deep, mid, smoothstep(0.05, 0.85, uv.y + n * 0.12));
	col = mix(col, lift, mist * 0.22 * (0.35 + u_calm));
	col = mix(col, warm, 0.08 * u_focus * (1.0 - uv.y));

	// Soft vignette
	float r = length((uv - 0.5) * vec2(1.25, 1.0));
	col *= 1.0 - 0.35 * smoothstep(0.55, 1.15, r);

	COLOR = vec4(col, 1.0);
}
