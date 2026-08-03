shader_type canvas_item;

// Calm (cool flowing field) ↔ Focus (warm energetic field).
// Balance pulls color/motion; blink detonates a radial flash.
uniform float u_time = 0.0;
uniform float u_calm = 0.5;
uniform float u_focus = 0.5;
uniform float u_blink = 0.0;
uniform float u_aspect = 1.777;

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
	for (int i = 0; i < 5; i++) {
		v += a * noise(p);
		p = p * 2.03 + vec2(1.7, 9.2);
		a *= 0.5;
	}
	return v;
}

void fragment() {
	vec2 uv = UV;
	vec2 p = uv * 2.0 - 1.0;
	p.x *= u_aspect;

	float calm = clamp(u_calm, 0.0, 1.0);
	float focus = clamp(u_focus, 0.0, 1.0);
	float bal = clamp(0.5 + 0.55 * (focus - calm), 0.0, 1.0);
	float energy = clamp(calm + focus, 0.15, 1.6);

	float t = u_time;
	// Slow field advection — calm/focus steer color more than churn the noise.
	float flow = t * (0.03 + 0.12 * focus + 0.04 * calm);
	float breathe = 1.0 + 0.025 * sin(t * (0.28 + 0.35 * calm)) * (0.35 + calm);

	vec2 q = p * breathe;
	// Domain warp: calm = soft drift, focus = sharper shear.
	vec2 w1 = vec2(
		fbm(q * (1.15 + focus) + vec2(flow, -0.3 * t)),
		fbm(q * (1.15 + focus) + vec2(-0.2 * t, flow * 0.85))
	);
	vec2 warped = q + (0.35 + 0.55 * calm) * (w1 - 0.5);
	warped.x += (focus - calm) * 0.22;
	float n = fbm(warped * mix(1.4, 3.2, focus) + vec2(0.0, flow * 0.4));
	float ridges = 1.0 - abs(2.0 * n - 1.0);
	ridges = pow(ridges, mix(1.6, 0.75, focus));

	// Soft filaments vs hard streaks.
	float filaments = smoothstep(0.35, 0.95, ridges);
	float streaks = pow(smoothstep(0.55, 1.0, ridges), mix(2.2, 0.9, focus));

	vec3 calm_deep = vec3(0.02, 0.06, 0.09);
	vec3 calm_mid = vec3(0.04, 0.42, 0.48);
	vec3 calm_hi = vec3(0.55, 0.92, 0.88);
	vec3 focus_deep = vec3(0.08, 0.03, 0.02);
	vec3 focus_mid = vec3(0.78, 0.38, 0.12);
	vec3 focus_hi = vec3(0.98, 0.82, 0.42);

	vec3 cool = mix(calm_deep, calm_mid, filaments);
	cool = mix(cool, calm_hi, filaments * filaments * (0.35 + 0.65 * calm));
	vec3 warm = mix(focus_deep, focus_mid, streaks);
	warm = mix(warm, focus_hi, pow(streaks, 1.4) * (0.4 + 0.6 * focus));

	vec3 col = mix(cool, warm, bal);
	col *= 0.55 + 0.55 * energy;

	// Soft vignette + left/right mood bias glow.
	float r = length(p);
	col *= 1.0 - 0.45 * smoothstep(0.75, 1.55, r);
	float left_g = exp(-pow((uv.x - 0.18) / 0.42, 2.0)) * calm;
	float right_g = exp(-pow((uv.x - 0.82) / 0.42, 2.0)) * focus;
	col += calm_mid * left_g * 0.18;
	col += focus_mid * right_g * 0.20;

	// Dual gauge arcs near bottom (visual, not UI chrome).
	vec2 gc = vec2(0.0, 0.72);
	vec2 gp = p - gc;
	float ang = atan(gp.x, -gp.y); // -PI..PI, 0 = up
	float ar = length(gp);
	float ring = smoothstep(0.028, 0.0, abs(ar - 0.38));
	float calm_arc = step(ang, mix(-2.6, 2.6, calm)) * step(-2.6, ang);
	float focus_arc = step(ang, mix(-2.6, 2.6, focus)) * step(-2.6, ang);
	// Split: cool arc left-ish, warm right-ish via x bias.
	float cool_mask = ring * calm_arc * smoothstep(0.15, -0.05, gp.x);
	float warm_mask = ring * focus_arc * smoothstep(-0.15, 0.05, gp.x);
	col = mix(col, calm_hi, cool_mask * 0.75);
	col = mix(col, focus_hi, warm_mask * 0.75);

	// Blink shockwave.
	float blink = clamp(u_blink, 0.0, 1.0);
	float wave = abs(r - (0.15 + 0.95 * (1.0 - blink)));
	float shock = blink * (1.0 - smoothstep(0.0, 0.12, wave));
	col = mix(col, vec3(1.0, 0.88, 0.72), shock * 0.9 + blink * 0.15);

	COLOR = vec4(col, 1.0);
}
