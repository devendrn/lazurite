from io import BytesIO
import os, json

from lazurite import util
from .variant import Variant
from ..platform import ShaderPlatform
from ..stage import ShaderStage
from .blend_mode import BlendMode
from .supported_platforms import SupportedPlatforms


class Pass:
    name: str
    supported_platforms: SupportedPlatforms
    fallback_pass: str
    default_blend_mode: BlendMode
    default_variant: dict[str, str]
    variants: list[Variant]

    def __init__(self):
        self.name = ""
        self.supported_platforms = SupportedPlatforms()
        self.fallback_pass = ""
        self.default_blend_mode = BlendMode.Unspecified
        self.default_variant = {}
        self.variants = []

    def read(self, file: BytesIO):
        self.name = util.read_string(file)
        self.supported_platforms = SupportedPlatforms(util.read_string(file))
        self.fallback_pass = util.read_string(
            file
        )  # (empty string) Fallback DoCheckerboarding DepthOnlyFallback

        if util.read_bool(file):  # Has default blend mode
            self.default_blend_mode = BlendMode[util.read_ushort(file)]

        self.default_variant = {}
        default_flag_count = util.read_ushort(file)
        for _ in range(default_flag_count):
            key = util.read_string(file)
            self.default_variant[key] = util.read_string(file)

        self.variants = [Variant().read(file) for _ in range(util.read_ushort(file))]

        return self

    def write(self, file: BytesIO):
        util.write_string(file, self.name)
        util.write_string(file, self.supported_platforms.get_bit_string())
        util.write_string(file, self.fallback_pass)

        util.write_bool(file, self.default_blend_mode != BlendMode.Unspecified)
        if self.default_blend_mode != BlendMode.Unspecified:
            util.write_ushort(file, self.default_blend_mode.value)

        util.write_ushort(file, len(self.default_variant))
        for key in self.default_variant:
            util.write_string(file, key)
            util.write_string(file, self.default_variant[key])

        util.write_ushort(file, len(self.variants))
        for variant in self.variants:
            variant.write(file)
        return self

    def serialize_properties(self):
        obj = {}
        obj["name"] = self.name
        obj["supported_platforms"] = self.supported_platforms.serialize()
        obj["fallback_pass"] = self.fallback_pass
        obj["default_blend_mode"] = (
            self.default_blend_mode.name
            if self.default_blend_mode != BlendMode.Unspecified
            else ""
        )
        obj["default_variant"] = self.default_variant
        obj["variants"] = []

        for i in range(len(self.variants)):
            obj["variants"].append(self.variants[i].serialize_properties(i))

        return obj

    def store(self, path: str = ".", skip_shaders=False):
        pass_dir = os.path.join(path, self.name)

        with open(os.path.join(path, f"{self.name}.json"), "w") as f:
            json.dump(self.serialize_properties(), f, indent=4)

        if skip_shaders:
            return self

        os.mkdir(pass_dir)

        for i in range(len(self.variants)):
            for shader in self.variants[i].shaders:
                with open(
                    os.path.join(pass_dir, shader.get_shader_file_name(i)), "wb"
                ) as f:
                    f.write(shader.bgfx_shader.shader_bytes)

        return self

    def load(self, object: dict, path: str):
        self.name = object.get("name", self.name)
        self.supported_platforms.load(object.get("supported_platforms", {}))
        self.fallback_pass = object.get("fallback_pass", self.fallback_pass)
        mode = object.get("default_blend_mode", None)
        if mode != None:
            self.default_blend_mode = BlendMode(mode) if mode else BlendMode.Unspecified
        self.default_variant = object.get("default_variant", self.default_variant)

        if "variants" in object:
            self.variants = [
                Variant().load(variant, os.path.join(path, self.name))
                for variant in object["variants"]
            ]
        return self

    def label(self, material_name: str):
        for variant_index, variant in enumerate(self.variants):
            variant.label(material_name, self.name, variant_index)

        return self

    def sort_variants(self):
        self.default_variant = dict(sorted(self.default_variant.items()))

        for variant in self.variants:
            variant.flags = dict(sorted(variant.flags.items()))

        self.variants.sort(key=lambda x: str(x.flags))

    def get_platforms(self):
        platforms: set[ShaderPlatform] = set()
        for variant in self.variants:
            platforms.update(variant.get_platforms())

        return platforms

    def get_stages(self):
        stages: set[ShaderStage] = set()
        for variant in self.variants:
            stages.update(variant.get_stages())

        return stages

    def merge_variants(self, other: "Pass"):
        for other_variant in other.variants:
            matching_variant = next(
                (v for v in self.variants if v.flags == other_variant.flags), None
            )
            if matching_variant is None:
                self.variants.append(other_variant)
            else:
                matching_variant.merge_variant(other_variant)

    def get_flag_definitions(self):
        """
        Returns a dict of all possible flag keys and their values.
        """
        definitions = {key: {value} for key, value in self.default_variant.items()}

        for variant in self.variants:
            for key, value in variant.flags.items():
                if key not in definitions:
                    definitions[key] = set()
                definitions[key].add(value)
        return definitions

    def add_platforms(self, platforms: set[ShaderPlatform]):
        for variant in self.variants:
            variant.add_platforms(platforms)

    def remove_platforms(self, platforms: set[ShaderPlatform]):
        for variant in self.variants:
            variant.remove_platforms(platforms)