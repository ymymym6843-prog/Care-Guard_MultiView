"""
Walking Aid 데이터셋 병합 스크립트

ELSA v3 + Mobility Aids v2 (nile-walker) → D:/WalkingAid_Dataset/

타겟 클래스 매핑:
  walker(0), cane(1), crutch(2), wheelchair(3)

ELSA v3 원본 클래스:
  0: crutches   → 2 (crutch)
  1: stroller   → 0 (walker)
  2: wheelchair → 3 (wheelchair)

Mobility Aids v2 원본 클래스:
  0: crutches       → 2 (crutch)
  1: person         → skip
  2: push_wheelchair→ 3 (wheelchair)
  3: walking_frame  → 0 (walker)
  4: wheelchair     → 3 (wheelchair)
"""

import shutil
from pathlib import Path

# ── 설정 ──
OUTPUT_DIR = Path("D:/WalkingAid_Dataset")
SOURCES = [
    {
        "name": "ELSA_v3",
        "root": Path("D:/Roboflow_Data/ELSA.v3i.yolov11"),
        "splits": {"train": "train", "val": "valid", "test": "test"},
        "class_map": {0: 2, 1: 0, 2: 3},  # crutches→crutch, stroller→walker, wheelchair→wheelchair
    },
    {
        "name": "MobilityAids_v2",
        "root": Path("D:/Roboflow_Data/Mobility Aids.v2i.yolov11"),
        "splits": {"train": "train", "val": "valid"},  # test 없음
        "class_map": {0: 2, 1: -1, 2: 3, 3: 0, 4: 3},  # person→skip
    },
]

TARGET_CLASSES = ["walker", "cane", "crutch", "wheelchair"]


def remap_label_file(src_path: Path, dst_path: Path, class_map: dict[int, int]) -> int:
    """라벨 파일을 리매핑하여 복사. 반환: 유효 라인 수."""
    lines = src_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        src_id = int(parts[0])
        target_id = class_map.get(src_id, -1)
        if target_id < 0:
            continue
        parts[0] = str(target_id)
        new_lines.append(" ".join(parts))

    if new_lines:
        dst_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return len(new_lines)


def merge():
    # 출력 디렉토리 생성
    for split in ("train", "val", "test"):
        (OUTPUT_DIR / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = {"total_images": 0, "total_labels": 0, "skipped": 0}
    class_counts = {i: 0 for i in range(len(TARGET_CLASSES))}

    for source in SOURCES:
        name = source["name"]
        root = source["root"]
        class_map = source["class_map"]

        print(f"\n[{name}] 처리 중... (root={root})")

        for target_split, src_split in source["splits"].items():
            src_img_dir = root / src_split / "images"
            src_lbl_dir = root / src_split / "labels"

            if not src_img_dir.exists():
                print(f"  [{target_split}] 이미지 디렉토리 없음: {src_img_dir}")
                continue

            img_files = sorted(src_img_dir.glob("*.*"))
            count = 0

            for img_file in img_files:
                if img_file.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                    continue

                # 파일명 충돌 방지: prefix 추가
                new_name = f"{name}_{img_file.name}"
                dst_img = OUTPUT_DIR / "images" / target_split / new_name

                # 라벨 파일 확인
                lbl_file = src_lbl_dir / (img_file.stem + ".txt")
                if not lbl_file.exists():
                    stats["skipped"] += 1
                    continue

                # 라벨 리매핑
                dst_lbl = OUTPUT_DIR / "labels" / target_split / (f"{name}_{img_file.stem}.txt")
                valid_lines = remap_label_file(lbl_file, dst_lbl, class_map)

                if valid_lines == 0:
                    # 유효한 보행도구 라벨이 없으면 스킵 (person-only 이미지 등)
                    stats["skipped"] += 1
                    continue

                # 이미지 복사
                shutil.copy2(str(img_file), str(dst_img))

                # 클래스별 카운트
                for line in dst_lbl.read_text(encoding="utf-8").splitlines():
                    cls_id = int(line.split()[0])
                    class_counts[cls_id] = class_counts.get(cls_id, 0) + 1

                count += 1

            stats["total_images"] += count
            stats["total_labels"] += count
            print(f"  [{target_split}] {count}장 복사 완료")

    # dataset.yaml 생성
    yaml_content = f"""path: {OUTPUT_DIR.as_posix()}
train: images/train
val: images/val
test: images/test

nc: {len(TARGET_CLASSES)}
names: {TARGET_CLASSES}
"""
    (OUTPUT_DIR / "dataset.yaml").write_text(yaml_content, encoding="utf-8")

    # 결과 출력
    print("\n" + "=" * 50)
    print(f"병합 완료: {OUTPUT_DIR}")
    print(f"총 이미지: {stats['total_images']}장")
    print(f"스킵 (person-only 등): {stats['skipped']}장")
    print(f"\n클래스별 바운딩박스 수:")
    for cls_id, cls_name in enumerate(TARGET_CLASSES):
        print(f"  {cls_id}: {cls_name:12s} = {class_counts.get(cls_id, 0):,}개")

    # split별 이미지 수
    print(f"\nSplit별 이미지 수:")
    for split in ("train", "val", "test"):
        n = len(list((OUTPUT_DIR / "images" / split).glob("*.*")))
        print(f"  {split}: {n}장")


if __name__ == "__main__":
    merge()
