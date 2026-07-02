# Case Study: Decoding an Obscured WhatsApp QR Photo

The source image was a camera photo of a WhatsApp QR code. It had three properties that made ordinary decoding fail:

- perspective skew from the camera angle
- yellow scanner guide brackets covering real QR modules
- a WhatsApp logo cutout in the center

Direct attempts failed with multiple local decoders:

- OpenCV `QRCodeDetector`
- OpenCV WeChat QR detector
- macOS Vision barcode detection
- Chrome `BarcodeDetector`
- `jsQR`
- `zxing-cpp`
- `quirc`

Preprocessing alone was not enough. Cropping, thresholding, masking the yellow guides, and perspective warping produced QR-like images, but the decoders still rejected them.

The working approach was geometric reconstruction:

1. Detect by eye that the finder-pattern distances matched a 33x33 module QR, which means Version 4.
2. Use the visible centers of the three finder patterns and the lower-right alignment pattern to define a homography.
3. Sample the photo once per QR module.
4. Restore standard function patterns.
5. Try every legal format-bit combination.
6. Render each candidate and ask a normal QR decoder to verify it.

The successful candidate decoded with:

- version: `4`
- threshold: `105`
- error-correction format index: `0`
- mask pattern: `4`

The private decoded URL is intentionally not included in this repository.
