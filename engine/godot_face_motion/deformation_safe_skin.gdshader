shader_type spatial;
render_mode cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D base_color_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform sampler2D orm_texture;
uniform float normal_strength : hint_range(0.0, 2.0, 0.01) = 1.0;
uniform float roughness_floor : hint_range(0.0, 1.0, 0.01) = 0.08;

vec3 deformation_safe_normal(vec3 view_position, vec2 uv, vec3 view_direction) {
    vec3 dpdx = dFdx(view_position);
    vec3 dpdy = dFdy(view_position);
    vec2 duvdx = dFdx(uv);
    vec2 duvdy = dFdy(uv);

    // Reconstruct the geometric normal from the actually rasterized/deformed
    // surface rather than trusting a pre-morph tangent frame.
    vec3 geometric_normal = normalize(cross(dpdx, dpdy));
    if (dot(geometric_normal, view_direction) < 0.0) {
        geometric_normal = -geometric_normal;
    }

    // Cotangent-frame reconstruction from position and UV derivatives. This
    // stays tied to the deformed triangle and naturally respects UV seams.
    vec3 dpdy_perp = cross(dpdy, geometric_normal);
    vec3 dpdx_perp = cross(geometric_normal, dpdx);
    vec3 tangent = dpdy_perp * duvdx.x + dpdx_perp * duvdy.x;
    vec3 bitangent = dpdy_perp * duvdx.y + dpdx_perp * duvdy.y;
    float basis_size = max(dot(tangent, tangent), dot(bitangent, bitangent));

    if (basis_size <= 1e-12) {
        return geometric_normal;
    }

    float inverse_basis = inversesqrt(basis_size);
    mat3 tangent_to_view = mat3(
        tangent * inverse_basis,
        bitangent * inverse_basis,
        geometric_normal
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

    // Fragment VERTEX and VIEW are in view space in the normal spatial-shader
    // path. The reconstructed frame therefore feeds NORMAL in the space Godot
    // expects without using imported TANGENT/BINORMAL blend-shape state.
    NORMAL = deformation_safe_normal(VERTEX, UV, VIEW);
}
