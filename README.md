# QR Photo Rescue

Recover hard-to-scan photographed QR codes by reconstructing the QR module grid from visible geometry.

This repo was born from a real rescue: a WhatsApp QR code photographed at an angle, partially covered by yellow scanner brackets and a center logo. Normal decoders could see QR-like structure but could not recover the payload. The breakthrough was to stop asking detectors to find the code and instead rebuild a clean QR image from the visible finder-pattern and alignment-pattern centers.

No images or private payloads from that recovery are included here.

## What Worked

The successful path was:

1. Identify the QR version from geometry. In the case study, the three finder patterns and lower-right alignment pattern matched a Version 4 QR code, which is a 33x33 module grid.
2. Use four control points:
   - top-left finder center
   - top-right finder center
   - bottom-left finder center
   - lower-right alignment-pattern center
3. Compute a homography from QR module coordinates to the photographed image.
4. Sample each module center into a boolean matrix.
5. Restore fixed QR function patterns that are known from the standard:
   - finder patterns
   - separators
   - timing patterns
   - alignment pattern
   - dark module
6. Brute-force the 32 legal QR format combinations: 4 error-correction levels x 8 mask patterns.
7. Render each reconstructed matrix as a clean QR image and feed it to a decoder.

That combination decoded a QR that failed with OpenCV `QRCodeDetector`, OpenCV WeChat QR, macOS Vision, Chrome `BarcodeDetector`, `jsQR`, `zxing-cpp`, and `quirc` on the raw/processed photo.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

## Usage

Pass the photographed QR image and four measured center points:

```bash
qr-photo-rescue path/to/photo.jpg \
  --version 4 \
  --top-left 336.5,190 \
  --top-right 915,208 \
  --bottom-left 343,750 \
  --alignment 842,714 \
  --thresholds 95:180:5 \
  --yellow-mask none \
  --out reconstructed-qr.png
```

The command prints the decoded payload when a candidate passes the decoder checksum and saves the reconstructed QR image.

For photos with yellow scanning guides over the modules, try:

```bash
--yellow-mask light
```

or:

```bash
--yellow-mask dark
```

## Finding Control Points

Open the image in any editor that shows pixel coordinates. Estimate the center of each visible pattern:

- Finder centers are the centers of the large square targets.
- For Version 2 and above, the lower-right alignment pattern is the smaller square target near the bottom-right of the QR data area.

The points do not need to be perfect, but they do need to land close to the centers. If decoding fails, adjust points by a few pixels and rerun.

## Why This Works

QR codes contain a lot of known structure. Even when a photo is too distorted or obstructed for a detector, the human-visible geometry can still define the QR grid. Once the grid is sampled, the fixed QR patterns and format bits can be repaired before handing a clean candidate to a normal decoder.

This is not magic: if too many data modules are truly hidden, Reed-Solomon error correction still has a limit. But for photos where the modules are mostly visible and the detector is the weak link, reconstruction can recover a valid payload.

## Privacy

The CLI runs locally. It does not upload images or payloads.

## License

MIT
