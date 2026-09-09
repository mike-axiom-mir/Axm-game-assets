shader_type spatial;
render_mode cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D base_color_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform sampler2D orm_texture;
uniform float normal_strength : hint_range(0.0, 2.0, 0.01) = 1.0;
uniform float roughness_floor : hint_range(0.0, 1.0, 0.01) = 0.08;

vec3 deformation_safe_normal(
    vec3 view_position,
    vec2 uv,
    vec3 smooth_deformed_normal,
    vec3 view_direction
) {
    vec3 dpdx = dFdx(view_position);
    vec3 dpdy = dFdy(view_position);
    vec2 duvdx = dFdx(uv);
    vec2 duvdy = dFdy(uv);

    // Godot already interpolates the blend-shape NORMAL state smoothly across
    // the deformed surface. Keep that smooth normal instead of replacing it
    // with a triangle face normal from cross(dFdx(P), dFdy(P)).
    vec3 surface_normal = normalize(smooth_deformed_normal);
    if (dot(surface_normal, view_direction) < 0.0) {
        surface_normal = -surface_normal;
    }

    // Rebuild only the UV tangent frame from derivatives of the already
    // deformed surface. This avoids the fragile imported morph TANGENT path
    // while retaining smooth vertex-normal shading and seam-local UV behavior.
    vec3 dpdy_perp = cross(dpdy, surface_normal);
    vec3 dpdx_perp = cross(surface_normal, dpdx);
    vec3 tangent = dpdy_perp * duvdx.x + dpdx_perp * duvdy.x;
    vec3 bitangent = dpdy_perp * duvdx.y + dpdx_perp * duvdy.y;
    float basis_size = max(dot(tangent, tangent), dot(bitangent, bitangent));

    if (basis_size <= 1e-12) {
        return surface_normal;
    }

    float inverse_basis = inversesqrt(basis_size);
    mat3 tangent_to_view = mat3(
        tangent * inverse_basis,
        bitangent * inverse_basis,
        surface_normal
    );

    vec3 mapped_normal = texture(normal_texture, uv).xyz * 2.0 - 1.0;
    mapped_normal.xy *= normal_strength;
    mapped_normal = normalize(mapped_normal);
    return normalize(tangent_to_view * mapped_normal);
}

void fragment() {
    vec4 base = texture(base_color_texture, UV);
    vec3 orm = texture(orm_texture, UV).rgb;

    ALBEDO = base.rgb;
    AO = orm.r;
    ROUGHNESS = max(roughness_floor, orm.g);
    METALLIC = 0.0;

    // VERTEX, NORMAL and VIEW are all in view space in Godot's normal spatial
    // shader path. NORMAL here includes the smooth deformed vertex-normal state.
    NORMAL = deformation_safe_normal(VERTEX, UV, NORMAL, VIEW);
}
