"""utils/utils.py — shared utilities: progress display and image extraction"""

import base64

try:
    from tqdm import tqdm as _tqdm

    def progress(iterable, position=0, leave=True, **kw):
        return _tqdm(iterable, position=position, leave=leave, **kw)

except ImportError:
    def progress(iterable, desc="", leave=True, **_):
        items = list(iterable)
        for i, item in enumerate(items, start=1):
            print(f"  {desc} {i}/{len(items)}", end="\r", flush=True)
            yield item
        if leave:
            print()


def extract_images_b64(page) -> list[str]:
    images = []
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        try:
            base_image = page.parent.extract_image(xref)
            img_bytes = base_image["image"]
            ext = base_image.get("ext", "png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            images.append(f"data:image/{ext};base64,{b64}")
        except Exception:
            pass
    return images
