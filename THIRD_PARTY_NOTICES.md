# Third-party and generated-asset notices

The project's [MIT license](LICENSE) covers its original source code, documentation and demonstration generator. It does not relicense dependencies, user-supplied LUTs or externally supplied images.

## Bundled working ICC

`reality_first_normalization/data/working_srgb.icc` is a generated LittleCMS sRGB profile, retained byte-for-byte as the working profile. Its embedded copyright field states:

> No copyright, use freely

SHA-256: `1e7c6b474ceb9dcf7796e85ccb898e5668d5c87d07b98d1ec702756e4e747706`.

This notice applies to that generated profile only. No commercial photographic profile, LUT, XMP preset or real photograph is bundled.

## Dependencies

Dependencies are installed separately by the package installer; their source and binary distributions retain their own notices. The following links identify the upstream projects' license texts, not replacement licenses for their distributions.

| Dependency | Role | Upstream project license |
| --- | --- | --- |
| NumPy | Array and numerical operations | [BSD-3-Clause](https://numpy.org/doc/stable/license.html), with additional component licenses in its distribution |
| Pillow | RGB image I/O, float resizing and LittleCMS interface | [MIT-CMU](https://pillow.readthedocs.io/en/stable/about.html#license), with additional bundled-library notices in its distribution |
| tifffile | TIFF input and 16-bit output | [BSD-3-Clause](https://github.com/cgohlke/tifffile/blob/master/LICENSE) |
| pytest | Test runner only | [MIT](https://docs.pytest.org/en/stable/license.html) |
| setuptools | Build backend | [MIT](https://github.com/pypa/setuptools/blob/main/LICENSE) |
| build | Development/CI build frontend | [MIT](https://github.com/pypa/build/blob/main/LICENSE) |

Runtime and test versions are recorded in `pyproject.toml`; executed versions are recorded in [VALIDATION.md](VALIDATION.md). The NumPy 2.4.6 distribution examined for this preview declares `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`; its included license files also describe bundled components. Pillow wheels likewise include notices for their bundled libraries. Preserve the complete notices from the actual dependency distributions when redistributing them.
