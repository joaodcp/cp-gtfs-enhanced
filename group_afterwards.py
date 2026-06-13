from utils.gtfsio import write_gtfs_zip, get_gtfs_zip
from grouping.group import get_grouped_gtfs
import os
import csv
import io

OUTPUT_DIR = "./enhanced"
ORIGINAL_GTFS_ZIP_PATH = os.getenv("GTFS_ZIP_PATH")
GTFS_ZIP_PATH = os.getenv("GTFS_TO_GROUP_ZIP_PATH")

original_gtfs_zip = get_gtfs_zip(ORIGINAL_GTFS_ZIP_PATH, None)
gtfs_zip = get_gtfs_zip(GTFS_ZIP_PATH, None)

routes_txt = original_gtfs_zip.read('routes.txt').decode('utf-8')
routes = list(csv.DictReader(io.StringIO(routes_txt)))

stops_txt = gtfs_zip.read('stops.txt').decode('utf-8')
stops = list(csv.DictReader(io.StringIO(stops_txt)))

trips_txt = gtfs_zip.read('trips.txt').decode('utf-8')
trips = list(csv.DictReader(io.StringIO(trips_txt)))

stop_times_txt = gtfs_zip.read('stop_times.txt').decode('utf-8')
stop_times = list(csv.DictReader(io.StringIO(stop_times_txt)))

grouped_gtfs = get_grouped_gtfs(
    {
        "routes": routes,
        "stops": stops,
        "trips": trips,
        "stop_times": stop_times
    }
)

output_path_grouped = write_gtfs_zip(
    OUTPUT_DIR,
    "cp_gtfs_grouped.zip",
    gtfs_zip,
    overrides={
        "routes.txt": grouped_gtfs["routes"],
        "trips.txt": grouped_gtfs["trips"],
    }
)

