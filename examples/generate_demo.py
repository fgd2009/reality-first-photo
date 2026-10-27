"""Generate original synthetic demonstrations, not photographs or branded film looks."""
import argparse
from pathlib import Path
import numpy as np
from reality_first_normalization.io import save_image


def generate(destination: Path):
    destination.mkdir(parents=True, exist_ok=False)
    images = destination / "input"
    images.mkdir()
    x = np.linspace(0, 1, 257, dtype=np.float32)
    ramp = np.tile(x[None, :, None], (97, 1, 3))
    chart = np.zeros((97, 257, 3), dtype=np.float32)
    for i, color in enumerate([(1,0,0), (0,1,0), (0,0,1), (.2,.4,.8), (.5,.5,.5)]):
        chart[:, i*51:(i+1)*51] = color
    geometry = np.zeros_like(chart) + .15
    geometry[10:70, 40:180] = (.7,.4,.2)
    geometry[35:90, 170:250] = (.2,.8,.4)
    for name, pixels in [("gradient", ramp), ("chart", chart), ("geometry", geometry)]:
        save_image(pixels, images / (name + ".png"))
    for name, transform in [("identity", lambda r,g,b:(r,g,b)), ("demo_warm", lambda r,g,b:(.04+.92*r,.96*g,.9*b))]:
        rows = ['# Original synthetic demonstration; not a commercial film look', 'LUT_3D_SIZE 2']
        rows += [' '.join(str(v) for v in transform(r,g,b)) for b in (0,1) for g in (0,1) for r in (0,1)]
        (destination / (name + ".cube")).write_text("\n".join(rows) + "\n")
    print("Generated 3 synthetic images and 2 original demonstration CUBEs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    generate(parser.parse_args().destination)
