"""
YOLO11n Walking Aid Detection - Fine-tuning + ONNX Export

Classes: walker(0), cane(1), crutch(2), wheelchair(3)

Usage:
    python scripts/training/train_walking_aid.py \
        --data D:/WalkingAid_Dataset \
        --output backend/models/walking_aid_yolo.onnx

Dataset layout (YOLO format):
    D:/WalkingAid_Dataset/
        images/
            train/  val/  test/
        labels/
            train/  val/  test/
"""

import argparse
import sys
import textwrap
from pathlib import Path


CLASS_NAMES = ["walker", "cane", "crutch", "wheelchair"]
CLASS_MAP = {
    # Roboflow "Mobility Aids" class aliases
    "walking_frame": 0,
    "walker": 0,
    "cane": 1,
    "crutches": 1,
    "crutch": 2,
    "wheelchair": 3,
    "push_wheelchair": 3,
    # Roboflow "ELSA" class aliases
    "stroller": 0,  # map stroller -> walker
}


def _create_dataset_yaml(data_dir: Path) -> Path:
    """Generate dataset.yaml for YOLO training."""
    yaml_path = data_dir / "dataset.yaml"

    # Determine split directories
    images_dir = data_dir / "images"
    if not images_dir.exists():
        # Flat structure: data_dir itself has train/val/test
        images_dir = data_dir

    content = textwrap.dedent(f"""\
        path: {data_dir.as_posix()}
        train: images/train
        val: images/val
        test: images/test

        nc: {len(CLASS_NAMES)}
        names: {CLASS_NAMES}
    """)
    yaml_path.write_text(content, encoding="utf-8")
    print(f"[INFO] dataset.yaml created: {yaml_path}")
    return yaml_path


def _remap_labels(data_dir: Path) -> None:
    """Remap label files from source dataset classes to our 4-class mapping.

    Reads a classes.txt if present, otherwise skips remapping.
    """
    classes_file = data_dir / "classes.txt"
    if not classes_file.exists():
        print("[INFO] No classes.txt found, skipping label remapping.")
        return

    # Read source class names
    source_classes = [
        line.strip().lower()
        for line in classes_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"[INFO] Source classes: {source_classes}")

    # Build source_id -> target_id mapping
    id_map: dict[int, int] = {}
    for src_id, src_name in enumerate(source_classes):
        if src_name in CLASS_MAP:
            id_map[src_id] = CLASS_MAP[src_name]
        elif src_name == "person":
            # Skip 'person' class (not a walking aid)
            id_map[src_id] = -1
        else:
            print(f"[WARN] Unknown source class '{src_name}' (id={src_id}), skipping")
            id_map[src_id] = -1

    if not id_map:
        return

    # Remap all label files
    labels_dir = data_dir / "labels"
    if not labels_dir.exists():
        return

    count = 0
    for label_file in labels_dir.rglob("*.txt"):
        if label_file.name == "classes.txt":
            continue
        lines = label_file.read_text(encoding="utf-8").splitlines()
        new_lines = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            src_id = int(parts[0])
            target_id = id_map.get(src_id, -1)
            if target_id < 0:
                continue  # skip unmapped classes
            parts[0] = str(target_id)
            new_lines.append(" ".join(parts))
        label_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        count += 1

    print(f"[INFO] Remapped {count} label files")


def train(data_dir: Path, output_path: Path, epochs: int = 50, imgsz: int = 640, batch: int = 16) -> None:
    """Fine-tune YOLO11n on walking aid dataset and export to ONNX."""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] ultralytics not installed. Run: pip install ultralytics")
        sys.exit(1)

    # Remap labels if needed
    _remap_labels(data_dir)

    # Create dataset.yaml
    yaml_path = _create_dataset_yaml(data_dir)

    # Load pre-trained YOLO11n (detection-only, NOT pose)
    print("[INFO] Loading yolo11n.pt base model...")
    model = YOLO("yolo11n.pt")

    # Fine-tune
    print(f"[INFO] Starting training: epochs={epochs}, imgsz={imgsz}, batch={batch}")
    results = model.train(
        data=str(yaml_path),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project=str(data_dir / "runs"),
        name="walking_aid",
        exist_ok=True,
        patience=10,
        lr0=0.01,
        lrf=0.01,
        mosaic=1.0,
        flipud=0.5,
        fliplr=0.5,
        verbose=True,
    )

    # Find best.pt
    best_pt = data_dir / "runs" / "walking_aid" / "weights" / "best.pt"
    if not best_pt.exists():
        print(f"[ERROR] best.pt not found at {best_pt}")
        sys.exit(1)

    print(f"[INFO] Training complete. Best model: {best_pt}")

    # Export to ONNX
    print("[INFO] Exporting to ONNX...")
    best_model = YOLO(str(best_pt))
    export_path = best_model.export(format="onnx", imgsz=imgsz, simplify=True)

    # Copy to output path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(export_path, str(output_path))
    print(f"[INFO] ONNX model saved: {output_path}")

    # Print validation metrics
    print("\n[INFO] Validation metrics:")
    val_results = best_model.val(data=str(yaml_path))
    print(f"  mAP50: {val_results.box.map50:.4f}")
    print(f"  mAP50-95: {val_results.box.map:.4f}")


def main():
    parser = argparse.ArgumentParser(description="Train YOLO11n Walking Aid Detector")
    parser.add_argument("--data", type=str, required=True, help="Dataset root directory (YOLO format)")
    parser.add_argument("--output", type=str, default="backend/models/walking_aid_yolo.onnx", help="Output ONNX path")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--remap-only", action="store_true", help="Only remap labels, do not train")
    args = parser.parse_args()

    data_dir = Path(args.data).resolve()
    output_path = Path(args.output).resolve()

    if not data_dir.exists():
        print(f"[ERROR] Dataset directory not found: {data_dir}")
        sys.exit(1)

    if args.remap_only:
        _remap_labels(data_dir)
        _create_dataset_yaml(data_dir)
        print("[INFO] Label remapping complete.")
        return

    train(data_dir, output_path, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch)


if __name__ == "__main__":
    main()
