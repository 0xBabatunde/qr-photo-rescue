from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
import zxingcpp


@dataclass(frozen=True)
class Point:
    x: float
    y: float


def bch_type_info(data: int) -> int:
    """Return the masked 15-bit QR format string for ECC/mask data."""
    generator = 0b10100110111
    mask = 0b101010000010010
    value = data << 10

    while value.bit_length() - generator.bit_length() >= 0:
        value ^= generator << (value.bit_length() - generator.bit_length())

    return ((data << 10) | value) ^ mask


def parse_point(text: str) -> Point:
    try:
        x_text, y_text = text.split(",", 1)
        return Point(float(x_text), float(y_text))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected point as x,y but got {text!r}"
        ) from exc


def qr_size(version: int) -> int:
    if not 1 <= version <= 40:
        raise ValueError("QR version must be in the range 1..40")
    return 21 + 4 * (version - 1)


def alignment_centers(version: int) -> list[int]:
    # QR alignment pattern center coordinates, from ISO/IEC 18004.
    table = {
        1: [],
        2: [6, 18],
        3: [6, 22],
        4: [6, 26],
        5: [6, 30],
        6: [6, 34],
        7: [6, 22, 38],
        8: [6, 24, 42],
        9: [6, 26, 46],
        10: [6, 28, 50],
    }
    if version not in table:
        raise ValueError("This demo CLI currently supports versions 1..10")
    return table[version]


def mask_yellow_guides(rgb: np.ndarray, mode: str) -> np.ndarray:
    if mode == "none":
        return rgb

    arr = rgb.astype(np.float32).copy()
    red, green, blue = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    mask = (
        (red > 165)
        & (green > 120)
        & (blue < 120)
        & ((red - blue) > 60)
        & ((green - blue) > 30)
    )

    for _ in range(3):
        mask = (
            mask
            | np.roll(mask, 1, axis=0)
            | np.roll(mask, -1, axis=0)
            | np.roll(mask, 1, axis=1)
            | np.roll(mask, -1, axis=1)
        )

    if mode == "light":
        arr[mask] = [235, 225, 240]
    elif mode == "dark":
        arr[mask] = [45, 45, 55]
    else:
        raise ValueError(f"unknown yellow mask mode: {mode}")

    return arr.astype(np.uint8)


def draw_finder(matrix: np.ndarray, row: int, col: int) -> None:
    size = matrix.shape[0]
    for rr in range(row - 1, row + 8):
        for cc in range(col - 1, col + 8):
            if 0 <= rr < size and 0 <= cc < size:
                matrix[rr, cc] = False

    for rr in range(7):
        for cc in range(7):
            matrix[row + rr, col + cc] = (
                rr in (0, 6)
                or cc in (0, 6)
                or (2 <= rr <= 4 and 2 <= cc <= 4)
            )


def draw_alignment(matrix: np.ndarray, center_row: int, center_col: int) -> None:
    size = matrix.shape[0]
    for rr in range(center_row - 2, center_row + 3):
        for cc in range(center_col - 2, center_col + 3):
            if 0 <= rr < size and 0 <= cc < size:
                distance = max(abs(rr - center_row), abs(cc - center_col))
                matrix[rr, cc] = distance == 2 or distance == 0


def restore_function_patterns(matrix: np.ndarray, version: int) -> None:
    size = matrix.shape[0]

    draw_finder(matrix, 0, 0)
    draw_finder(matrix, 0, size - 7)
    draw_finder(matrix, size - 7, 0)

    for col in range(8, size - 8):
        matrix[6, col] = col % 2 == 0
    for row in range(8, size - 8):
        matrix[row, 6] = row % 2 == 0

    matrix[size - 8, 8] = True

    centers = alignment_centers(version)
    for row in centers:
        for col in centers:
            overlaps_top_left = row < 9 and col < 9
            overlaps_top_right = row < 9 and col > size - 10
            overlaps_bottom_left = row > size - 10 and col < 9
            if overlaps_top_left or overlaps_top_right or overlaps_bottom_left:
                continue
            draw_alignment(matrix, row, col)


def set_format_bits(matrix: np.ndarray, ecc_level: int, mask_pattern: int) -> None:
    size = matrix.shape[0]
    bits = bch_type_info((ecc_level << 3) | mask_pattern)

    for i in range(15):
        value = ((bits >> i) & 1) == 1
        if i < 6:
            matrix[i, 8] = value
        elif i < 8:
            matrix[i + 1, 8] = value
        else:
            matrix[size - 15 + i, 8] = value

    for i in range(15):
        value = ((bits >> i) & 1) == 1
        if i < 8:
            matrix[8, size - i - 1] = value
        elif i < 9:
            matrix[8, 15 - i] = value
        else:
            matrix[8, 15 - i - 1] = value

    matrix[size - 8, 8] = True


def bilinear(gray: np.ndarray, x: float, y: float) -> float:
    height, width = gray.shape
    if x < 0 or y < 0 or x >= width - 1 or y >= height - 1:
        return 255.0

    x0, y0 = int(math.floor(x)), int(math.floor(y))
    dx, dy = x - x0, y - y0
    return float(
        gray[y0, x0] * (1 - dx) * (1 - dy)
        + gray[y0, x0 + 1] * dx * (1 - dy)
        + gray[y0 + 1, x0] * (1 - dx) * dy
        + gray[y0 + 1, x0 + 1] * dx * dy
    )


def sample_matrix(
    rgb: np.ndarray,
    version: int,
    image_points: list[Point],
    threshold: int,
) -> np.ndarray:
    size = qr_size(version)
    gray = np.dot(rgb[..., :3], [0.299, 0.587, 0.114]).astype(np.float32)

    qr_points = np.float32(
        [
            [3.5, 3.5],
            [size - 3.5, 3.5],
            [3.5, size - 3.5],
            [alignment_centers(version)[-1] + 0.5, alignment_centers(version)[-1] + 0.5],
        ]
    )
    target_points = np.float32([[p.x, p.y] for p in image_points])
    homography = cv2.getPerspectiveTransform(qr_points, target_points)

    matrix = np.zeros((size, size), dtype=bool)
    for row in range(size):
        for col in range(size):
            qr_point = np.array([col + 0.5, row + 0.5, 1.0])
            image_point = homography @ qr_point
            x = image_point[0] / image_point[2]
            y = image_point[1] / image_point[2]
            matrix[row, col] = bilinear(gray, x, y) < threshold

    return matrix


def render_matrix(matrix: np.ndarray, scale: int = 16, border: int = 4) -> Image.Image:
    size = matrix.shape[0]
    image = Image.new("L", ((size + 2 * border) * scale, (size + 2 * border) * scale), 255)
    draw = ImageDraw.Draw(image)

    for row in range(size):
        for col in range(size):
            if matrix[row, col]:
                x = (col + border) * scale
                y = (row + border) * scale
                draw.rectangle([x, y, x + scale - 1, y + scale - 1], fill=0)

    return image


def decode_image(image: Image.Image) -> str | None:
    for result in zxingcpp.read_barcodes(image):
        if result.text:
            return result.text
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recover a photographed QR code by reconstructing its module grid "
            "from finder-pattern and alignment-pattern center points."
        )
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("--version", type=int, default=4)
    parser.add_argument("--top-left", type=parse_point, required=True)
    parser.add_argument("--top-right", type=parse_point, required=True)
    parser.add_argument("--bottom-left", type=parse_point, required=True)
    parser.add_argument("--alignment", type=parse_point, required=True)
    parser.add_argument("--thresholds", default="95:180:5")
    parser.add_argument("--yellow-mask", choices=["none", "light", "dark"], default="none")
    parser.add_argument("--out", type=Path, default=Path("reconstructed-qr.png"))
    return parser


def threshold_values(spec: str) -> list[int]:
    if ":" not in spec:
        return [int(value) for value in spec.split(",") if value]

    start, stop, step = [int(value) for value in spec.split(":")]
    return list(range(start, stop + 1, step))


def main() -> int:
    args = build_parser().parse_args()
    source = np.array(Image.open(args.image).convert("RGB"))
    source = mask_yellow_guides(source, args.yellow_mask)

    points = [args.top_left, args.top_right, args.bottom_left, args.alignment]
    attempts = 0
    for threshold in threshold_values(args.thresholds):
        matrix = sample_matrix(source, args.version, points, threshold)
        restore_function_patterns(matrix, args.version)

        for ecc_level in range(4):
            for mask_pattern in range(8):
                candidate = matrix.copy()
                set_format_bits(candidate, ecc_level, mask_pattern)
                rendered = render_matrix(candidate)
                attempts += 1

                payload = decode_image(rendered)
                if payload:
                    rendered.save(args.out)
                    print(payload)
                    print(
                        f"decoded with threshold={threshold}, "
                        f"ecc_level={ecc_level}, mask_pattern={mask_pattern}",
                    )
                    print(f"wrote {args.out}")
                    return 0

    print(f"no decode after {attempts} candidates")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
