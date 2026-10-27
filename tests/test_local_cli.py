"""End-to-end local CLI on programmatically generated pixels/LUTs only."""
import hashlib
import json
import runpy
import sys
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from reality_first_normalization import io
from reality_first_normalization import local_cli


def fixture(tmp_path):
    folder=tmp_path/'input';folder.mkdir()
    x=np.linspace(0,1,257,dtype=np.float32)
    ramp=np.tile(x[None,:,None],(97,1,3))
    chart=np.zeros((97,257,3),dtype=np.float32)
    for n,rgb in enumerate([(1,0,0),(0,1,0),(0,0,1),(.2,.4,.8),(.5,.5,.5)]): chart[:,n*51:(n+1)*51]=rgb
    geo=np.zeros_like(chart)+.15;geo[10:70,40:180]=(.7,.4,.2);geo[35:90,170:250]=(.2,.8,.4)
    for name,arr in [('gradient',ramp),('chart',chart),('geometry',geo)]: io.save_image(arr,folder/(name+'.png'))
    cubes={}
    for name,fn in [('identity',lambda r,g,b:(r,g,b)),('demo_warm',lambda r,g,b:(.04+.92*r,.96*g,.9*b))]:
        p=tmp_path/(name+'.cube')
        p.write_text('LUT_3D_SIZE 2\n'+'\n'.join(' '.join(str(v) for v in fn(r,g,b)) for b in (0,1) for g in (0,1) for r in (0,1)))
        cubes[name]=p
    return folder,cubes


def invoke(args,monkeypatch):
    # Exercise __main__, argparse and the real CLI path, without child processes.
    monkeypatch.delitem(sys.modules,'reality_first_normalization.local_cli',raising=False)
    monkeypatch.setattr(sys,'argv',['reality_first_normalization.local_cli',*map(str,args)])
    with pytest.raises(SystemExit) as ended:
        runpy.run_module('reality_first_normalization.local_cli',run_name='__main__')
    return ended.value.code


def digest(folder):return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}


def test_cli_identity_batch_and_repeat_import(tmp_path,monkeypatch):
    source,cubes=fixture(tmp_path);before=digest(source);out=tmp_path/'identity'
    args=['--input',source,'--output',out,'--lut',cubes['identity'],'--normalize-strength','0','--format','tiff']
    assert invoke(args,monkeypatch)==0
    manifest=json.loads((out/'manifest.json').read_text());assert manifest['status']=='complete' and len(manifest['items'])==3
    for original in source.glob('*.png'):
        a,_=io.load_image(original,read_metadata=False)
        b,_=io.load_image(out/(original.stem+'.tif'),read_metadata=False)
        assert b.shape==(97,257,3) and np.max(np.abs(a-b))<=1/65535
        with io.tifffile.TiffFile(out/(original.stem+'.tif')) as tif:assert tif.pages[0].iccprofile==io.working_srgb_icc()
    output_before=digest(out)
    assert invoke(args,monkeypatch)==2
    assert digest(out)==output_before and digest(source)==before
    args[3]=tmp_path/'repeat';assert invoke(args,monkeypatch)==0
    assert digest(source)==before


def test_cli_custom_lut_strength_and_resize(tmp_path,monkeypatch):
    source,cubes=fixture(tmp_path);original=source/'chart.png';before=digest(source)
    for strength in [0,.5,1]:
        out=tmp_path/f'warm-{strength}'
        assert invoke(['--input',original,'--output',out,'--lut',cubes['demo_warm'],'--normalize-strength','0','--lut-strength',strength,'--format','png'],monkeypatch)==0
        src,_=io.load_image(original,read_metadata=False);result,_=io.load_image(out/'chart.png',read_metadata=False)
        desired=src*(1-strength)+np.stack((.04+.92*src[...,0],.96*src[...,1],.9*src[...,2]),axis=-1)*strength
        assert np.max(np.abs(result-desired))<=1/255
    out=tmp_path/'normalize-resize'
    assert invoke(['--input',source,'--output',out,'--normalize-strength','.6','--max-long-edge','128','--format','jpeg'],monkeypatch)==0
    for p in out.glob('*.jpg'):
        with Image.open(p) as image:assert image.size==(128,48) and image.info['icc_profile']==io.working_srgb_icc()
    assert digest(source)==before


def test_cli_missing_lut_no_output_and_untagged_rejected(tmp_path,monkeypatch):
    source,cubes=fixture(tmp_path);out=tmp_path/'missing'
    assert invoke(['--input',source,'--output',out,'--lut',tmp_path/'missing.cube'],monkeypatch)==2
    assert not out.exists()
    untagged=tmp_path/'untagged.png';Image.new('RGB',(8,8),(50,100,150)).save(untagged)
    rejected=tmp_path/'rejected'
    assert invoke(['--input',untagged,'--output',rejected],monkeypatch)==2
    assert json.loads((rejected/'manifest.json').read_text())['status']=='failed'
    assert not list(rejected.glob('*.tif'))
    assert invoke(['--input',untagged,'--output',tmp_path/'declared','--assume-srgb'],monkeypatch)==0


def test_cli_cancel_marks_partial_output(tmp_path,monkeypatch):
    source,cubes=fixture(tmp_path);out=tmp_path/'cancelled'
    def cancel(*args,**kwargs):raise KeyboardInterrupt()
    monkeypatch.setattr(local_cli,'load_image',cancel)
    assert local_cli.main(['--input',str(source),'--output',str(out)])==130
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['status']=='cancelled' and manifest['items']==[]


def test_cli_default_preview_size_and_explicit_full_size(tmp_path, monkeypatch):
    source = tmp_path / "wide_synthetic.png"
    pixels = np.tile(np.linspace(.1, .9, 4096, dtype=np.float32)[None, :, None], (4, 1, 3))
    io.save_image(pixels, source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    for label, extra, size in [("preview", [], (2048, 2)), ("full", ["--max-long-edge", "0"], (4096, 4))]:
        out = tmp_path / label
        assert invoke(["--input", source, "--output", out, "--normalize-strength", "0", *extra], monkeypatch) == 0
        with io.tifffile.TiffFile(out / "wide_synthetic.tif") as tif:
            assert tif.pages[0].shape == (size[1], size[0], 3)
            assert tif.pages[0].iccprofile == io.working_srgb_icc()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_cli_mixed_raw_folder_rejected_before_any_export(tmp_path):
    source, _ = fixture(tmp_path)
    (source / "unsupported.dng").write_bytes(b"synthetic unsupported input")
    before = digest(source)
    output = tmp_path / "output"
    assert local_cli.main(["--input", str(source), "--output", str(output)]) == 2
    assert not output.exists()
    assert digest(source) == before
