import csv
import io
import os
import zipfile

import requests

def get_gtfs_zip(path, url):
    if path and os.path.exists(path):
        print(f"Using local GTFS zip: {path}")
        return zipfile.ZipFile(path, 'r')

    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    return zipfile.ZipFile(io.BytesIO(response.content))

def write_gtfs_zip(
    output_dir: str,
    output_filename: str,
    gtfs_zip: zipfile.ZipFile,
    overrides: dict,  # {"stops.txt": stops, "stop_times.txt": stop_times}
    skip_files=None
):
    skip_files = set(skip_files or [])

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_filename)

    print(f"creating gtfs package at {output_path}...")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as out_zip:

        # write overridden tables
        for filename, rows in overrides.items():
            if not rows:
                continue

            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

            out_zip.writestr(filename, buffer.getvalue())
            print(f"wrote {filename}")

        # copy everything else
        for file_info in gtfs_zip.filelist:
            name = file_info.filename

            if name in overrides or name in skip_files:
                continue

            out_zip.writestr(name, gtfs_zip.read(name))
            print(f"copied {name}")

    return output_path
