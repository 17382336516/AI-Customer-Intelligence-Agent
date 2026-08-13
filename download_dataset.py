"""Acquire the official Tianchi source file without bypassing Tianchi authentication."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

OFFICIAL_DATASET_PAGE = "https://tianchi.aliyun.com/dataset/dataDetail?dataId=46"
DEFAULT_NAME = "tianchi_mobile_recommend_train_user.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_source(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Source file does not exist: {source}")
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "benchmark-builder/1.0"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as out:
            shutil.copyfileobj(response, out, length=1024 * 1024)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def extract_csv(archive: Path, output_dir: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        members = [name for name in bundle.namelist() if name.lower().endswith(".csv")]
        if not members:
            raise ValueError("The downloaded ZIP archive contains no CSV file.")
        preferred = next((name for name in members if Path(name).name == DEFAULT_NAME), members[0])
        destination = output_dir / Path(preferred).name
        with bundle.open(preferred) as source, destination.open("wb") as out:
            shutil.copyfileobj(source, out, length=1024 * 1024)
        return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Save the official Tianchi Taobao APP behavior file under data/raw."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--source-file", type=Path, help="Official file already downloaded")
    source.add_argument("--url", help="Authenticated/signed official Tianchi download URL")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--filename", help="Saved filename; defaults to the local source name")
    parser.add_argument("--sha256", dest="expected_sha256", help="Optional expected SHA-256")
    args = parser.parse_args()

    if not args.source_file and not args.url:
        parser.error(
            "Tianchi requires an authenticated download. Download from "
            f"{OFFICIAL_DATASET_PAGE}, then pass --source-file, or pass an official signed --url."
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    filename = args.filename or (args.source_file.name if args.source_file else DEFAULT_NAME)
    destination = args.output_dir / filename
    if args.source_file:
        copy_source(args.source_file, destination)
    else:
        download(args.url, destination)

    actual_sha256 = sha256(destination)
    if args.expected_sha256 and actual_sha256.lower() != args.expected_sha256.lower():
        destination.unlink(missing_ok=True)
        raise ValueError("SHA-256 mismatch; the downloaded file was removed.")

    if zipfile.is_zipfile(destination):
        archive = destination
        if archive.suffix.lower() != ".zip":
            archive = destination.with_suffix(".zip")
            destination.replace(archive)
            destination = archive
        data_file = extract_csv(archive, args.output_dir)
    else:
        data_file = destination

    print(f"Saved: {destination.resolve()}")
    if data_file != destination:
        print(f"Extracted CSV: {data_file.resolve()}")
    print(f"SHA-256: {actual_sha256}")
    print(f"Source page: {OFFICIAL_DATASET_PAGE}")


if __name__ == "__main__":
    main()
