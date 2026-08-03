shader_type canvas_item;

// Soft dawn/dusk sky behind the meditation tree.
uniform float u_time = 0.0;
uniform float u_calm = 0.5;
uniform float u_growth = 0.0;
uniform float u_blink = 0.0;

void fragment() {
	float y = UV.y;
	float calm = clamp(u_calm, 0.0, 1.0);
	float g = clamp(u_growth, 0.0, 1.0);

	vec3 zenith = mix(vec3(0.10, 0.16, 0.22), vec3(0.18, 0.38, 0.48), calm);
	vec3 horizon = mix(vec3(0.22, 0.18, 0.14), vec3(0.55, 0.62, 0.48), 0.35 + 0.45 * g);
	vec3 ground = vec3(0.08, 0.11, 0.07);

	vec3 sky = mix(zenith, horizon, smoothstep(0.0, 0.72, y));
	sky = mix(sky, ground, smoothstep(0.78, 1.0, y));

	// Gentle mist bands.
	float mist = 0.04 * sin(UV.x * 6.0 + u_time * 0.15) * calm;
	sky += vec3(mist * 0.6, mist * 0.85, mist);

	// Sunrise bloom as the tree matures.
	float sun_y = mix(0.62, 0.38, g);
	float d = length(UV - vec2(0.72, sun_y));
	sky += vec3(0.55, 0.42, 0.18) * exp(-d * mix(14.0, 7.0, g)) * (0.25 + 0.55 * g);

	sky = mix(sky, vec3(0.95, 0.9, 0.78), clamp(u_blink, 0.0, 1.0) * 0.35);
	COLOR = vec4(sky, 1.0);
}
