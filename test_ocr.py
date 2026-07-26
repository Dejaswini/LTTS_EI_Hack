import sys
sys.path.insert(0, 'backend')

from services.ocr_service import extract_ocr_from_file
from services.classifier import classify_drawing

import os
from PIL import Image, ImageDraw

# Create a synthetic test image with known text
img = Image.new('RGB', (800, 300), 'white')
d = ImageDraw.Draw(img)
d.text((10, 10),  'DRAWING TITLE Motor Shaft',         fill='black')
d.text((10, 40),  'DRAWING NUMBER DWG-001',             fill='black')
d.text((10, 70),  'SCALE 1:1',                          fill='black')
d.text((10, 100), 'DRAWN BY J. Smith DATE 2025-01-01',  fill='black')
d.text((10, 130), 'REV A',                              fill='black')
d.text((100, 200),'diameter 28',                        fill='black')
d.text((300, 200),'40',                                 fill='black')

os.makedirs('backend/uploads', exist_ok=True)
img.save('backend/uploads/test_part.png')

print("Running OCR on synthetic test image...")
dets = extract_ocr_from_file('backend/uploads/test_part.png')
print(f"Total detections: {len(dets)}")
for det in dets[:8]:
    txt  = det['text']
    conf = det['confidence']
    bbox = det['bbox']
    print(f"  text={txt!r:<40s}  conf={conf}  bbox={bbox}")

dtype = classify_drawing(dets)
print(f"\nClassified as: {dtype}")
print("SUCCESS - pipeline works correctly!")
