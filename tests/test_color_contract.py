"""Independent synthetic reference tests for the bounded SDR color contract."""
import hashlib
import itertools
import struct
import zlib
from io import BytesIO

import numpy as np
import pytest
from PIL import Image, ImageCms

from reality_first_normalization import io
from reality_first_normalization.lut import apply_cube_lut, load_cube_lut


@pytest.fixture(autouse=True)
def no_exif_subprocess(monkeypatch):
    monkeypatch.setattr(io, 'read_exif', lambda path: {})


def linear_rgb_icc():
    # Generated source profile: same primaries/description as our working ICC,
    # but parametric type-3 TRCs are exactly linear. No third-party profile data.
    data=bytearray(io.working_srgb_icc())
    count=struct.unpack_from('>I',data,128)[0]
    seen=set()
    for index in range(count):
        tag, offset, _size = struct.unpack_from('>4sII', data, 132 + 12 * index)
        if tag in {b'rTRC',b'gTRC',b'bTRC'}:
            assert data[offset:offset+4]==b'para' and struct.unpack_from('>H',data,offset+8)[0]==3
            struct.pack_into('>5i',data,offset+12,65536,65536,0,65536,0)
            seen.add(tag)
    assert len(seen)==3
    data[84:100]=bytes(16)
    return bytes(data)


def srgb_encode(linear):
    return np.where(linear <= .0031308, 12.92*linear, 1.055*linear**(1/2.4)-.055)


def scalar_trilinear(pixel, rows, n, lower, upper):
    # Independent flat-row reference: Adobe Cube 1.0 §7.2, r + N*g + N*N*b.
    coordinates=[min(max((float(pixel[i])-lower[i])/(upper[i]-lower[i]),0),1)*(n-1) for i in range(3)]
    lows=[int(np.floor(x)) for x in coordinates]
    fractions=[coordinates[i]-lows[i] for i in range(3)]
    result=[0.,0.,0.]
    for corner in itertools.product((0,1), repeat=3):
        r,g,b=[min(lows[i]+corner[i],n-1) for i in range(3)]
        weight=1.
        for i in range(3): weight*=fractions[i] if corner[i] else 1-fractions[i]
        row=rows[r+n*g+n*n*b]
        for channel in range(3):result[channel]+=weight*row[channel]
    return result


def test_cube_asymmetric_random_table_matches_independent_flat_scalar(tmp_path):
    n=3;lower=(-.25,.1,.3);upper=(1.25,1.1,2.3)
    rows=np.random.default_rng(47).random((n**3,3))
    path=tmp_path/'generated_asymmetric.cube'
    lines=['LUT_3D_SIZE 3','DOMAIN_MIN -.25 .1 .3','DOMAIN_MAX 1.25 1.1 2.3']
    lines += [' '.join(f'{v:.12f}' for v in row) for row in rows]
    path.write_text('\n'.join(lines))
    pixels=np.random.default_rng(113).uniform(-.3,2.5,size=(7,11,3)).astype(np.float32)
    expected=np.array([[scalar_trilinear(p,rows,n,lower,upper) for p in row] for row in pixels])
    assert np.max(np.abs(apply_cube_lut(pixels,load_cube_lut(str(path)))-expected)) < 2e-6


@pytest.mark.parametrize('domain',['DOMAIN_MIN 1 0 0\nDOMAIN_MAX 1 1 1','DOMAIN_MIN nan 0 0','DOMAIN_MAX -1 1 1'])
def test_invalid_cube_domains_rejected(tmp_path,domain):
    p=tmp_path/'invalid.cube';p.write_text('LUT_3D_SIZE 2\n'+domain+'\n'+'0 0 0\n'*8)
    with pytest.raises(ValueError,match='DOMAIN'):load_cube_lut(str(p))


def test_linear_rgb8_is_converted_not_relabelled(tmp_path):
    src_icc=linear_rgb_icc()
    src=tmp_path/'linear.png';dst=tmp_path/'encoded.png'
    values=np.array([8,32,64,128,192,240],dtype=np.uint8)
    rgb=np.tile(values[None,:,None],(2,1,3))
    Image.fromarray(rgb).save(src,icc_profile=src_icc)
    pixels,metadata=io.load_image(src)
    expected=srgb_encode(rgb.astype(np.float64)/255)
    assert np.max(np.abs(pixels-expected)) <= 2/255
    assert round(float(pixels[0,3,0])*255) in range(187,190)
    assert not np.allclose(pixels,rgb/255,atol=.01)
    assert metadata['InputICC_SHA256']==hashlib.sha256(src_icc).hexdigest()
    assert metadata['WorkingICC_SHA256']==hashlib.sha256(io.working_srgb_icc()).hexdigest()
    assert metadata['ColorConversion']=='lcms_rgb8_to_working_srgb'
    io.save_image(pixels,dst)
    with Image.open(dst) as out:
        assert out.info['icc_profile']==io.working_srgb_icc()!=src_icc
        assert np.max(np.abs(np.asarray(out)/255-expected)) <= 2/255


def test_tagged_working_rgb8_roundtrip_near_identity(tmp_path):
    src=tmp_path/'working.png'
    rgb=np.random.default_rng(5).integers(0,256,(9,13,3),dtype=np.uint8)
    Image.fromarray(rgb).save(src,icc_profile=io.working_srgb_icc())
    arr,metadata=io.load_image(src)
    assert np.max(np.abs(arr-rgb/255)) < 1e-6
    assert metadata['WorkingColorSpace'].startswith('sRGB')


def test_untagged_requires_explicit_assumption(tmp_path):
    p=tmp_path/'untagged.png';Image.new('RGB',(4,4),(20,80,190)).save(p)
    with pytest.raises(io.ColorManagementError,match='ICC'):io.load_image(p)
    pixels,metadata=io.load_image(p,assume_srgb=True)
    assert np.allclose(pixels[0,0],np.array([20,80,190])/255)
    assert metadata['ColorConversion']=='explicit_assume_srgb_untagged_rgb8'


def test_broken_icc_cannot_be_bypassed_by_assumption(tmp_path):
    p=tmp_path/'bad.png';Image.new('RGB',(4,4)).save(p,icc_profile=b'invalid-profile')
    with pytest.raises(io.ColorManagementError,match='ICC'):io.load_image(p,assume_srgb=True)


def test_high_depth_same_name_different_transfer_profile_rejected(tmp_path):
    assert io.tifffile is not None
    src=linear_rgb_icc()
    source_description=ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(BytesIO(src)))
    working_description=ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(BytesIO(io.working_srgb_icc())))
    assert source_description==working_description
    p=tmp_path/'linear16.tiff'
    io.tifffile.imwrite(p,np.ones((3,4,3),dtype=np.uint16)*32768,photometric='rgb',iccprofile=src)
    with pytest.raises(io.ColorManagementError,match='High-depth TIFF'):io.load_image(p,assume_srgb=True)


def test_untagged_tiff16_explicit_assumption_and_range(tmp_path):
    assert io.tifffile is not None
    p=tmp_path/'untagged16.tiff';data=np.arange(48,dtype=np.uint16).reshape(4,4,3)*1000
    io.tifffile.imwrite(p,data,photometric='rgb')
    with pytest.raises(io.ColorManagementError,match='ICC'):io.load_image(p)
    arr,metadata=io.load_image(p,assume_srgb=True)
    assert np.max(np.abs(arr-data/65535)) < 1e-6
    assert metadata['ColorConversion']=='explicit_assume_srgb_untagged_high_depth'


def test_tiff_export_never_silently_falls_back_to_8bit(tmp_path,monkeypatch):
    monkeypatch.setattr(io,'tifffile',None)
    with pytest.raises(io.ColorManagementError,match='8-bit'):
        io.save_image(np.zeros((3,4,3),dtype=np.float32),tmp_path/'out.tiff')


def test_jpeg_output_declares_working_icc_and_is_8bit(tmp_path):
    p=tmp_path/'out.jpg';io.save_image(np.ones((8,8,3),dtype=np.float32)*.5,p)
    with Image.open(p) as image:
        assert image.info['icc_profile']==io.working_srgb_icc()
        assert np.asarray(image).dtype==np.uint8


def test_nonworking_export_requires_conversion(tmp_path):
    with pytest.raises(io.ColorManagementError,match='sRGB'):
        io.save_image(np.zeros((3,4,3)),tmp_path/'out.png',color_space='Display P3')


def test_png16_rejected_before_pillow_can_reduce_precision(tmp_path):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,16,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0'+struct.pack('>HHH',1000,2000,3000)))+chunk(b'IEND',b'')
    p=tmp_path/'rgb16.png';p.write_bytes(data)
    with pytest.raises(io.ColorManagementError,match='High-depth PNG'):io.load_image(p,assume_srgb=True)


def test_raw_explicitly_unavailable_without_invoking_decoder(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('must not decode or read EXIF')
    monkeypatch.setattr(io,'read_exif',forbidden)
    with pytest.raises(io.ColorManagementError,match='RAW is unsupported'):io.load_image(tmp_path/'generated.dng')


@pytest.mark.parametrize('mode,extra',[('RGBA',{}),('RGB',{'transparency':(0,0,0)})])
def test_transparency_is_not_silently_discarded(tmp_path,mode,extra):
    p=tmp_path/'transparent.png'
    Image.new(mode,(4,4)).save(p,icc_profile=io.working_srgb_icc(),**extra)
    with pytest.raises(io.ColorManagementError):io.load_image(p)


@pytest.mark.parametrize('actual',['PNG','TIFF'])
def test_misnamed_content_cannot_bypass_decoder_contract(tmp_path,actual):
    p=tmp_path/'misnamed.jpg'
    if actual=='PNG':
        Image.new('RGB',(3,3)).save(p,format='PNG',icc_profile=io.working_srgb_icc())
    else:
        io.tifffile.imwrite(p,np.ones((3,3,3),dtype=np.uint16),photometric='rgb',iccprofile=io.working_srgb_icc())
    with pytest.raises(io.ColorManagementError,match='does not match its extension'):io.load_image(p)


def test_packed_tiff_bit_depth_is_rejected_before_decode(tmp_path):
    # Synthetic header alteration: advertised 12-bit samples must be rejected,
    # even though a decoder would expose them as uint16. No imagecodecs needed.
    p=tmp_path/'twelve_bit_declaration.tiff'
    io.tifffile.imwrite(p,np.ones((3,3,3),dtype=np.uint16),photometric='rgb',iccprofile=io.working_srgb_icc())
    with io.tifffile.TiffFile(p) as tif:
        tag=tif.pages[0].tags['BitsPerSample'];offset=tag.valueoffset;count=tag.count;endian=tif.byteorder
    data=bytearray(p.read_bytes());struct.pack_into(endian+'H'*count,data,offset,*([12]*count));p.write_bytes(data)
    with pytest.raises(io.ColorManagementError,match='bit depth'):io.load_image(p)


@pytest.mark.parametrize('outside',[-.1,1.1])
def test_extended_range_cube_is_rejected_not_preclipped(tmp_path,outside):
    p=tmp_path/'extended.cube'
    rows=['LUT_3D_SIZE 2']+['0 0 0']*7+[f'{outside} 0 0']
    p.write_text('\n'.join(rows))
    with pytest.raises(ValueError,match='SDR preview'):load_cube_lut(str(p))


def test_narrow_cube_domain_keeps_its_defined_scale(tmp_path):
    p=tmp_path/'narrow.cube'
    rows=['LUT_3D_SIZE 2','DOMAIN_MIN 0 0 0','DOMAIN_MAX .00000001 .00000001 .00000001']
    rows += [f'{r} {g} {b}' for b in (0,1) for g in (0,1) for r in (0,1)]
    p.write_text('\n'.join(rows))
    pixels=np.array([[[2e-9,5e-9,8e-9]]],dtype=np.float64)
    assert np.max(np.abs(apply_cube_lut(pixels,load_cube_lut(str(p)))-np.array([[[.2,.5,.8]]]))) < 1e-6


def test_compressed_tiff_declaration_is_rejected_before_decode(tmp_path):
    import struct
    p = tmp_path / "synthetic_compression_declaration.tif"
    io.tifffile.imwrite(p, np.zeros((3, 3, 3), dtype=np.uint16), photometric="rgb", iccprofile=io.working_srgb_icc())
    with io.tifffile.TiffFile(p) as tif:
        offset = tif.pages[0].tags["Compression"].valueoffset
        byteorder = tif.byteorder
    data = bytearray(p.read_bytes())
    data[offset:offset + 2] = struct.pack(byteorder + "H", 5)
    p.write_bytes(data)
    with pytest.raises(io.ColorManagementError, match="uncompressed TIFF"):
        io.load_image(p, read_metadata=False)


def test_cube_title_accepts_tab_separator(tmp_path):
    p = tmp_path / "tab_title.cube"
    p.write_text('TITLE\t"Identity"\nLUT_3D_SIZE 2\n' + '\n'.join(f'{r} {g} {b}' for b in (0, 1) for g in (0, 1) for r in (0, 1)))
    lut = load_cube_lut(str(p))
    assert lut.title == "Identity"
    pixels = np.array([[[.2, .4, .8]]], dtype=np.float32)
    assert np.max(np.abs(apply_cube_lut(pixels, lut) - pixels)) < 1e-6


def test_animated_png_rejected_instead_of_silently_selecting_first_frame(tmp_path):
    p = tmp_path / "animated.png"
    first = Image.new("RGB", (4, 4), (10, 20, 30))
    second = Image.new("RGB", (4, 4), (90, 100, 110))
    first.save(p, save_all=True, append_images=[second], duration=100,
               icc_profile=io.working_srgb_icc())
    with Image.open(p) as image:
        assert image.n_frames == 2
    with pytest.raises(io.ColorManagementError, match="Multi-frame"):
        io.load_image(p, read_metadata=False)
