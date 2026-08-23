# -*- coding: utf-8 -*-
"""
把 camo_dataset/ 里非 jpg/png 的图（webp、heif 等）转成 png。
PNG 无损，保留所有色彩信息和 alpha 通道，适合做 COD 数据集。

用法：
    python convert_to_png.py            # 默认转 png
    python convert_to_png.py --jpg      # 转 jpg（高质量 q=95，文件更小，但有损）
    python convert_to_png.py --keep     # 保留原文件（默认会删）
"""

import json
import sys
from pathlib import Path

# 注册 heif opener
from pillow_heif import register_heif_opener
register_heif_opener()

from PIL import Image

OUTPUT_DIR = Path("camo_dataset")
META_PATH  = OUTPUT_DIR / "_pins_meta.json"
SRC_EXTS   = {".webp", ".heif", ".heic"}


def main():
    target = "jpg" if "--jpg" in sys.argv else "png"
    keep   = "--keep" in sys.argv
    quality = 95  # jpg 质量

    files = sorted(
        p for p in OUTPUT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SRC_EXTS
    )
    if not files:
        print(f"没有需要转换的文件（{SRC_EXTS}）")
        return

    print(f"待转换: {len(files)} 个 → .{target}")
    if not keep:
        print("（转换成功后会删除原文件，加 --keep 保留）")

    success = 0
    for i, src in enumerate(files, 1):
        pin_id = src.stem.replace("huaban_", "")
        dst = OUTPUT_DIR / f"{src.stem}.{target}"
        try:
            with Image.open(src) as img:
                # 处理某些格式的透明通道
                if target == "jpg" and img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                save_kw = {}
                if target == "jpg":
                    save_kw["quality"] = quality
                    save_kw["subsampling"] = 0  # 不降采样，保留细节
                img.save(dst, **save_kw)
            src_size = src.stat().st_size
            dst_size = dst.stat().st_size
            print(
                f"  [{i}/{len(files)}] {src.name} "
                f"({src_size//1024} KB) → {dst.name} "
                f"({dst_size//1024} KB, {img.size[0]}x{img.size[1]})"
            )
            if not keep:
                src.unlink()
            success += 1
        except Exception as e:
            print(f"  [{i}/{len(files)}] ✗ {src.name}: {e!r}")

    # 更新元数据里的 type 字段
    if META_PATH.exists() and not keep:
        try:
            pins = json.loads(META_PATH.read_text(encoding="utf-8"))
            updated = 0
            for p in pins:
                t = (p.get("file") or {}).get("type", "")
                if any(t.endswith(ext) for ext in (".webp", ".heif", ".heic", "webp", "heif", "heic")):
                    p["file"]["type"] = f"image/{target}"
                    p["_converted"] = True
                    updated += 1
            if updated:
                META_PATH.write_text(
                    json.dumps(pins, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"\n更新了 {updated} 个 pin 的 type 字段（→ image/{target}）")
        except Exception as e:
            print(f"\n更新元数据失败（不影响文件转换）: {e!r}")

    print(f"\n完成: 成功 {success} / 失败 {len(files)-success} / 总共 {len(files)}")


if __name__ == "__main__":
    main()
