"""Place reference and real synthetic render in the SAME QA comparison input."""
from pathlib import Path
import sys
from PIL import Image, ImageDraw

source, actual, output = map(Path,sys.argv[1:4])
output.mkdir(parents=True,exist_ok=True)
with Image.open(source) as image:
    reference = image.convert('RGB').resize((1440,1024),Image.Resampling.LANCZOS)
with Image.open(actual) as image:
    rendered = image.convert('RGB')
assert rendered.size == (1440,1024),rendered.size
for name,box in (('full',(0,0,1440,1024)),('inspector',(860,200,1440,850)),
                 ('header',(0,0,1440,225)),('footer',(220,860,1440,1024))):
    left,right = reference.crop(box),rendered.crop(box)
    canvas = Image.new('RGB',(left.width*2,left.height+28),'#e7edf2')
    canvas.paste(left,(0,28))
    canvas.paste(right,(left.width,28))
    draw = ImageDraw.Draw(canvas)
    draw.text((12,7),'APPROVED CONCEPT',fill='#173247')
    draw.text((left.width+12,7),'ACTUAL DESKCHECK — SYNTHETIC FAILURE',fill='#173247')
    canvas.save(output/(name+'.png'))
print(output)
