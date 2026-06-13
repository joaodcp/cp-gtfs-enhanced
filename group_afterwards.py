from utils.gtfsio import write_gtfs_zip, get_gtfs_zip
from grouping.group import get_grouped_gtfs
import os

OUTPUT_DIR = "./enhanced"
GTFS_ZIP_PATH = os.getenv("GTFS_TO_GROUP_ZIP_PATH")

gtfs_zip = get_gtfs_zip(GTFS_ZIP_PATH, None)

grouped_gtfs = get_grouped_gtfs(gtfs_zip)

output_path_grouped = write_gtfs_zip(
    OUTPUT_DIR,
    "cp_gtfs_grouped.zip",
    gtfs_zip,
    overrides={
        "routes.txt": grouped_gtfs["routes"],
        "trips.txt": grouped_gtfs["trips"],
    }
)

