# Real-camera RAW samples

Checked on raw.pixls.us on 2026-11-02. Each row below was CC0 1.0 in `https://raw.pixls.us/json/getrepository.php?set=all`, and the sha256 matches `https://raw.pixls.us/data/filelist.sha256`. The files are not in git.

| Camera | File | Bytes | sha256 | License |
| --- | --- | --- | --- | --- |
| Canon EOS R, CRAW 1.6x crop | [Canon_EOS_R_CRAW_ISO_100_crop_nodual.CR3](https://raw.pixls.us/data/Canon/EOS%20R/Canon_EOS_R_CRAW_ISO_100_crop_nodual.CR3) | 7997663 | `90bbf397b592f9ce9799477df4affbdf0025578c07eac26f928696b0d40d5121` | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |
| Nikon D7000, 12-bit compressed | [Compressed 12-bit D7000 NIK_3876.NEF](https://raw.pixls.us/data/Nikon/D7000/Compressed%2012-bit%20D7000%20NIK_3876.NEF) | 13048000 | `986db2bf9ed08cf095bb94cfbaf02f0e89d123edad28b63c05133e7815749486` | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |
| Olympus E-M10 | [P3180165.ORF](https://raw.pixls.us/data/Olympus/E-M10/P3180165.ORF) | 15258356 | `d7f6ac99ee1f824e81ec0e71599f0f87f9b2e2675f7ddfdb21202281b8bdc5e0` | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |
| Panasonic DMC-GH4, 1:1 | [P1010607.RW2](https://raw.pixls.us/data/Panasonic/DMC-GH4/P1010607.RW2) | 14388224 | `3764eb2f2399b1b035739dbdda55f5db78751a2c4ffcc07690fbe5b5e4b` | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |

The default test job skips these. A separate `real-raw-samples` job downloads them, checks the sha256, and decodes each file twice. Locally:

```sh
python -m pip install -e '.[test]'
python -m pytest -q -m realraw tests/test_real_raw.py
```

Cache directory: `$REALITY_FIRST_RAW_CACHE` or `~/.cache/reality-first-photo/raw-samples`. If the network is down, or rawpy is not installed, the test skips. A checksum mismatch is a failure.

The assertion is the [RAW contract](RAW_CONTRACT.md): 16-bit path, encoded sRGB shape, rawpy and LibRaw versions, camera white balance, AHD, `gamma=1,1`, and a bit-identical second decode. It does not compare the picture with a camera JPEG.
