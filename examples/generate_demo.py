"""Compatibility entry point for generating original synthetic inputs and LUTs."""
import argparse
from pathlib import Path

from reality_first_normalization.demo import generate


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    generate(parser.parse_args().destination)
