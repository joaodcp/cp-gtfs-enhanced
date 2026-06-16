from utils.gtfsio import write_gtfs_zip, get_gtfs_zip
from grouping.group import get_grouped_gtfs
from utils.names import get_fixed_name

from datetime import datetime
import os
import csv
import io


OUTPUT_DIR = "./enhanced"
ORIGINAL_GTFS_ZIP_PATH = os.getenv("GTFS_ZIP_PATH")
GTFS_ZIP_PATH = os.getenv("GTFS_TO_GROUP_ZIP_PATH")
NEW_AGENCY_ID = '3'
NEW_AGENCY_NAME = "Comboios de Portugal"

MISSING_ROUTE_SERVICE_COLORS = {
    'AP': '#7b9a40',
    'IC': '#33703c',
    'IR': '#3c70b3',
    'R': '#de833c',
    'U': '#4e98d1',
    'IN': '#702351'
}

original_gtfs_zip = get_gtfs_zip(ORIGINAL_GTFS_ZIP_PATH, None)
gtfs_zip = get_gtfs_zip(GTFS_ZIP_PATH, None)

agency_txt = original_gtfs_zip.read('agency.txt').decode('utf-8')
agency = list(csv.DictReader(io.StringIO(agency_txt)))

routes_txt = original_gtfs_zip.read('routes.txt').decode('utf-8')
routes = list(csv.DictReader(io.StringIO(routes_txt)))

stops_txt = gtfs_zip.read('stops.txt').decode('utf-8')
stops = list(csv.DictReader(io.StringIO(stops_txt)))

trips_txt = gtfs_zip.read('trips.txt').decode('utf-8')
trips = list(csv.DictReader(io.StringIO(trips_txt)))

stop_times_txt = gtfs_zip.read('stop_times.txt').decode('utf-8')
stop_times = list(csv.DictReader(io.StringIO(stop_times_txt)))

for route in routes:
    new_color = MISSING_ROUTE_SERVICE_COLORS.get(route['route_short_name'])[1:] if route['route_short_name'] in MISSING_ROUTE_SERVICE_COLORS else None
    if new_color:
        route['route_color'] = new_color if new_color else 'FFFFFF'
        route['route_text_color'] = 'FFFFFF' if new_color else '000000'
    route['agency_id'] = NEW_AGENCY_ID

agency[0]['agency_id'] = NEW_AGENCY_ID
agency[0]['agency_name'] = NEW_AGENCY_NAME

for stop in stops:
    stop['stop_name'] = get_fixed_name(stop['stop_name'])

grouped_gtfs = get_grouped_gtfs(
    {
        "routes": routes,
        "stops": stops,
        "trips": trips,
        "stop_times": stop_times
    },
    agency_id_replace=NEW_AGENCY_ID
)

feed_info = [{
    "feed_publisher_name": "CP - Comboios de Portugal; joaodcp",
    "feed_publisher_url": "https://github.com/joaodcp/cp-gtfs-enhanced#cp_gtfs_groupedzip",
    "feed_lang": "pt",
    "feed_version": datetime.now().strftime("%Y-%m-%d"),
    # start of current year
    "feed_start_date": datetime(datetime.now().year, 1, 1).strftime("%Y%m%d"),
    # end of current year
    "feed_end_date": datetime(datetime.now().year, 12, 31).strftime("%Y%m%d"),
}]

output_path_grouped = write_gtfs_zip(
    OUTPUT_DIR,
    "cp_gtfs_grouped.zip",
    gtfs_zip,
    overrides={
        "agency.txt": agency,
        "routes.txt": grouped_gtfs["routes"],
        "trips.txt": grouped_gtfs["trips"],
        "stops.txt": stops,
        "feed_info.txt": feed_info
    }
)

