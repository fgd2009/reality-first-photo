"""CC0 camera RAW files checked on raw.pixls.us on 2026-11-02.

The files themselves are not in git. Tests download them into a cache directory
and check the sha256 published by raw.pixls.us.
"""
from __future__ import annotations

SAMPLES = (
    {
        "id": "canon-eos-r-craw-1.6x-crop",
        "camera": "Canon EOS R",
        "mode": "CRAW 1.6x crop, ISO 100",
        "url": "https://raw.pixls.us/data/Canon/EOS%20R/Canon_EOS_R_CRAW_ISO_100_crop_nodual.CR3",
        "filename": "Canon_EOS_R_CRAW_ISO_100_crop_nodual.CR3",
        "sha256": "90bbf397b592f9ce9799477df4affbdf0025578c07eac26f928696b0d40d5121",
        "bytes": 7997663,
        "license": "CC0 1.0",
        "listed": "https://raw.pixls.us/json/getrepository.php?set=all",
        "repository_date": "2021-05-14",
    },
    {
        "id": "nikon-d7000-12bit-compressed",
        "camera": "Nikon D7000",
        "mode": "12-bit compressed",
        "url": "https://raw.pixls.us/data/Nikon/D7000/Compressed%2012-bit%20D7000%20NIK_3876.NEF",
        "filename": "Compressed 12-bit D7000 NIK_3876.NEF",
        "sha256": "986db2bf9ed08cf095bb94cfbaf02f0e89d123edad28b63c05133e7815749486",
        "bytes": 13048000,
        "license": "CC0 1.0",
        "listed": "https://raw.pixls.us/json/getrepository.php?set=all",
        "repository_date": "2017-01-22",
    },
    {
        "id": "olympus-e-m10",
        "camera": "Olympus E-M10",
        "mode": "16-bit ORF",
        "url": "https://raw.pixls.us/data/Olympus/E-M10/P3180165.ORF",
        "filename": "P3180165.ORF",
        "sha256": "d7f6ac99ee1f824e81ec0e71599f0f87f9b2e2675f7ddfdb21202281b8bdc5e0",
        "bytes": 15258356,
        "license": "CC0 1.0",
        "listed": "https://raw.pixls.us/json/getrepository.php?set=all",
        "repository_date": "2017-04-10",
    },
    {
        "id": "panasonic-dmc-gh4-1-1",
        "camera": "Panasonic DMC-GH4",
        "mode": "1:1 RW2",
        "url": "https://raw.pixls.us/data/Panasonic/DMC-GH4/P1010607.RW2",
        "filename": "P1010607.RW2",
        "sha256": "3764eb2f2399b1b035739dbdda55f5db78751a2c4ffab4ffcc07690fbe5b5e4b",
        "bytes": 14388224,
        "license": "CC0 1.0",
        "listed": "https://raw.pixls.us/json/getrepository.php?set=all",
        "repository_date": "2018-05-10",
    },
)
