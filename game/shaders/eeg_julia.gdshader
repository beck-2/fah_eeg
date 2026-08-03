shader_type canvas_item;

// EEG-driven Julia set — calm softens, focus sharpens/warps, blink detonates.
uniform float u_time = 0.0;
uniform vec2 u_c = vec2(-0.8, 0.156);
uniform float u_zoom = 1.35;
uniform vec2 u_center = vec2(0.0, 0.0);
uniform float u_calm = 0.4;
uniform float u_focus = 0.4;
uniform float u_blink = 0.0;
uniform float u_aspect = 1.777;

vec3 palette(float t, float calm, float blink) {
	// Deep ocean → teal → amber (no purple defaults).
	vec3 a = vec3(0.02, 0.05, 0.08);
	vec3 b = vec3(0.05, 0.55, 0.62);
	vec3 ccol = vec3(0.95, 0.62, 0.22);
	vec3 d = vec3(0.98, 0.92, 0.78);
	float soft = mix(t, pow(t, 0.65), calm);
	vec3 cold = mix(a, b, smoothstep(0.0, 0.45, soft));
	vec3 warm = mix(b, ccol, smoothstep(0.35, 0.8, soft));
	vec3 hot = mix(ccol, d, smoothstep(0.7, 1.0, soft));
	vec3 col = mix(cold, warm, smoothstep(0.25, 0.55, soft));
	col = mix(col, hot, smoothstep(0.55, 0.95, soft));
	col = mix(col, vec3(1.0, 0.75, 0.55), blink * 0.85);
	return col;
}

void fragment() {
	vec2 uv = UV * 2.0 - 1.0;
	uv.x *= u_aspect;
	uv = uv / max(u_zoom, 0.05) + u_center;

	float breathe = 1.0 + 0.04 * sin(u_time * (0.6 + u_calm)) * u_calm;
	uv *= breathe;

	vec2 z = uv;
	vec2 jc = u_c;
	float max_i = mix(48.0, 96.0, clamp(u_focus, 0.0, 1.0));

	float escaped = 0.0;
	float smooth_i = 0.0;
	vec2 z_esc = z;

	// Fixed upper bound for Metal / Godot RD compatibility.
	for (int n = 0; n < 96; n++) {
		float fi = float(n);
		if (escaped < 0.5 && fi < max_i) {
			z = vec2(z.x * z.x - z.y * z.y, 2.0 * z.x * z.y) + jc;
			if (dot(z, z) > 12.0) {
				escaped = 1.0;
				z_esc = z;
				float mod2 = length(z_esc);
				smooth_i = fi + 1.0 - log(log(max(mod2, 1.0001))) / log(2.0);
			}
		}
	}

	if (escaped < 0.5) {
		float glow = 0.15 + 0.35 * u_calm + 0.55 * u_blink;
		COLOR = vec4(vec3(0.08, 0.03, 0.02) * glow + vec3(0.02, 0.04, 0.05), 1.0);
	} else {
		float t = clamp(smooth_i / max(max_i, 1.0), 0.0, 1.0);
		vec3 col = palette(t, u_calm, u_blink);
		float r = length(UV * 2.0 - 1.0);
		col *= 1.0 - 0.35 * smoothstep(0.7, 1.4, r);
		COLOR = vec4(col, 1.0);
	}
}
