# Bounded SDR color contract

Status: CLI preview prepared for public release. The owner has authorized publication of the original source under MIT. This contract covers local processing of synthetic test inputs; it makes no real-photo, physical-film or GUI validation claim. See [VALIDATION.md](../VALIDATION.md) for the current environment, installation, test and build evidence.

## Processing contract

The working space is encoded sRGB with floating-point RGB arrays in [0,1]. Normalization and style changes operate on these working-space coordinates. They do not change the declared primaries or transfer function. The export API accepts only this working-space contract; it never copies the input ICC blindly.

### LUT file layout and interpolation

Adobe Cube 1.0 section 7.2 defines flat row index `r + N*g + N*N*b`: red changes fastest. The loader explicitly maps file [b,g,r,channel] order to internal [r,g,b,channel] indexing. A separate scalar implementation using flat rows verifies asymmetric random tables and non-default domains; it does not call the vector renderer to obtain expected values. Identity, cross-channel functions and a 1e-8-wide domain are covered.

This preview supports 3D tables of size 2..256, finite positive DOMAIN ranges and output nodes in [0,1]. Unsupported directives (including 1D/combined tables and LUT_3D_INPUT_RANGE), malformed fields and duplicate declarations fail explicitly; they are never ignored. HDR/extended-range output nodes are rejected instead of preclipped. It uses trilinear interpolation, not the tetrahedral interpolation recommended by the specification, and does not claim full CUBE conformance. LUTs must be authored for the encoded sRGB working space; no log/P3/scene-linear input transform is inferred from the file.

The old reader treated blue as fastest. Old results can therefore change. There is no silent legacy wrong-axis mode. Previously generated custom files that used the wrong layout must be explicitly regenerated/reordered after identifying their provenance; no existing user LUT was read or changed during this repair.

### Precision

Resizing uses three Pillow F-mode float32 planes with Lanczos filtering and an explicit [0,1] clamp. It does not quantize through uint8. This is precision preservation in encoded RGB, not a claim of physically linear-light resampling. A 4096-level source ramp resized to 2048 pixels retains 2048 distinct levels. TIFF16 export quantizes once to 16 bits; JPEG and PNG export are intentionally 8-bit, and JPEG is lossy.

### ICC policy

`reality_first_normalization/data/working_srgb.icc` was generated once using the installed Pillow/LittleCMS. It is versioned and reused byte-for-byte. SHA-256: `1e7c6b474ceb9dcf7796e85ccb898e5668d5c87d07b98d1ec702756e4e747706`. Its generated copyright field states “No copyright, use freely”. No third-party photographic profile was downloaded.

RGB8 inputs carrying valid RGB ICC profiles are converted through LittleCMS to this working profile using relative colorimetric intent, then converted to float arrays. Reports retain input/workspace profile hashes and conversion decisions. All supported exports embed the working profile, never the unconverted source profile.

Only uncompressed, single-page interleaved RGB TIFF is accepted; compressed TIFF is explicitly rejected without installing extra decoders. High-depth RGB TIFF data bypasses Pillow and stays in NumPy/tifffile. It is accepted only if its ICC is byte-identical to the fixed working profile, or if it has no profile and the caller explicitly declares `assume_srgb=True`. Even colorimetrically equivalent external sRGB profiles may be rejected: arbitrary high-depth CMS conversion has not been implemented. Profile names do not establish equivalence. A differently encoded synthetic profile with the same name is rejected for TIFF16.

Untagged images are rejected by default. `load_image(..., assume_srgb=True)` is an explicit Python API assumption available only when the caller knows the encoding. It cannot bypass a corrupt or unsupported embedded profile. The local CLI provides `--assume-srgb` for the same deliberate declaration. No native UI control has been validated. Unsupported modes, alpha/color-key transparency, format/extension mismatches, packed TIFF sample depths, multi-page TIFF, multi-frame PNG/JPEG, non-default TIFF orientation, and 16-bit PNG are rejected rather than silently altered.

## Support matrix

| Path | Current core behavior | Validation |
|---|---|---|
| Tagged RGB8 JPEG/PNG | ICC conversion to work sRGB | Synthetic pixels/ICC |
| RGB8 TIFF | ICC conversion to work sRGB | Guarded implementation; no real-photo claims |
| RGB16/float32 TIFF | Native precision; fixed work ICC or explicit untagged sRGB assumption | Synthetic TIFF16 roundtrip/guards |
| JPEG/PNG output | 8-bit work sRGB with ICC | Synthetic checks |
| TIFF output | 16-bit work sRGB with ICC; requires existing tifffile | Synthetic roundtrip |
| RAW/DNG | Explicitly unavailable in this recovery preview | Rejection tested; no decoder invoked |
| Native GUI / Windows / macOS application packaging | Outside this CLI preview | Not validated |
| Python wheel / source distribution | Built and installed on Linux with Python 3.12 | See current validation record |
| Commercial LUTs/XMP | Not copied or evaluated; missing assets fail closed | Synthetic missing-asset guards |

RAW is unavailable because output primaries alone do not establish a transfer curve. A future RAW path needs an explicit decode/encoding contract plus real RAW validation. Nothing here claims physical film reproduction or Adobe rendering equivalence.

The local CLI defaults to a 2048-pixel preview long edge. Full resolution requires `--max-long-edge 0`; large-image memory/performance is unverified. Input decoding precedes resizing, so this is not a total memory bound.

## Verification and sources

The current synthetic regression suite and installed CLI exports are recorded in [VALIDATION.md](../VALIDATION.md). Historical test counts from other source trees are not combined with this suite. The CLI has no network or model-call implementation. The local regression run disables automatic pytest plugin loading; it does not claim to implement an operating-system network sandbox.

Independent numerical checks require flat scalar/trilinear error <2e-6, narrow-domain error <1e-6, TIFF16 roundtrip error <=1/65535, and linear-RGB code 128 to convert to encoded-sRGB code 187–189 (rather than remain 128). The ICC check uses a programmatically generated linear RGB source profile with unchanged name/primaries, plus the independent IEC sRGB transfer equation; it verifies changed pixels and the correct output profile.

Sources are referenced for facts, not copied as implementation code:

- [Adobe Cube LUT Specification 1.0, section 7.2 (Adobe-authored PDF mirror)](https://kono.phpage.fr/images/a/a1/Adobe-cube-lut-specification-1.0.pdf). The old Adobe-hosted URL returned 404; no sample C++ code or PDF is bundled.
- [ICC sRGB encoding registry](https://registry.color.org/rgb-registry/srgb): primaries and transfer function used for the independent expected values.
- [Pillow ImageCms documentation](https://pillow.readthedocs.io/en/latest/reference/ImageCms.html): LittleCMS profile transformation interface. Executed dependency versions are recorded separately in the local test evidence.
