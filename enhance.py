from time import sleep, time, timezone
from zoneinfo import ZoneInfo
import requests
import zipfile
import io
import csv
import json
import os
from datetime import date, datetime
from grouping.group import get_grouped_gtfs
from utils.names import get_fixed_name
from utils.time import normalize_gtfs_time, get_gtfs_time_from_utc_millis
from services.adif import get_adif_arrivals, get_adif_circulation
from utils.gtfsio import write_gtfs_zip, get_gtfs_zip

is_gha = os.getenv("GITHUB_ACTIONS") == "true"

GTFS_URL = "https://publico.cp.pt/gtfs/gtfs.zip"
OUTPUT_DIR = "./enhanced"
CP_GIS_API_URL = "https://api-gateway.cp.pt/cp/services/gis-api/train-path/{trip_short_name}"
GTFS_ZIP_PATH = os.getenv("GTFS_ZIP_PATH")

MISSING_INTERNATIONAL_STOPS = [
    {
        "stop_id": "71_37606",
        "stop_name": "Badajoz",
        "stop_lat": 38.8923683166504,
        "stop_lon": -6.9839301109314,
        "location_type": "0",
        "stop_timezone": "Europe/Madrid",
        "wheelchair_boarding": "0"
    },
    {
        "stop_id": "71_22308",
        "stop_name": "Vigo-Guixar",
        "stop_lat": 42.2394905090332,
        "stop_lon": -8.83141708374023,
        "location_type": "0",
        "stop_timezone": "Europe/Madrid",
        "wheelchair_boarding": "0"
    }
]

MISSING_ROUTE_SERVICE_COLORS = {
    'AP': '#7b9a40',
    'IC': '#33703c',
    'IR': '#3c70b3',
    'R': '#de833c',
    'U': '#4e98d1',
    'IN': '#702351'
}

def get_station_arrivals(station_id, date, start_time):
    res = requests.get(
        f"https://api-gateway.cp.pt/cp/services/travel-api/stations/{station_id}/timetable/{date}?start={start_time}",
        headers={
            'x-api-key': os.getenv("CP_TRAVEL_API_KEY"),
            'x-cp-connect-id': os.getenv("CP_TRAVEL_CONNECT_ID"),
            'x-cp-connect-secret': os.getenv("CP_TRAVEL_CONNECT_SECRET"),
            'User-Agent': os.getenv("USER_AGENT", "cp-gtfs-enhanced/1.0")
        }
    )
    res.raise_for_status()
    return res.json()['stationStops']

def get_trip_details(trip_ids):
    print("Fetching trip details for trips:", trip_ids)
    res = requests.post(
        "https://api-gateway.cp.pt/cp/services/realtime-api/trains/details",
        json=trip_ids,
        headers={
            'x-api-key': os.getenv("CP_REALTIME_API_KEY"),
            'x-cp-connect-id': os.getenv("CP_REALTIME_CONNECT_ID"),
            'x-cp-connect-secret': os.getenv("CP_REALTIME_CONNECT_SECRET"),
            'User-Agent': os.getenv("USER_AGENT", "cp-gtfs-enhanced/1.0")
        }
    )
    res.raise_for_status()
    return res.json()

def get_planned_trip_details(train_number, date = datetime.now().strftime("%Y-%m-%d")):
    print(f"Fetching planned trip details for train {train_number} on {date}")
    res = requests.get(
        f"https://api-gateway.cp.pt/cp/services/travel-api/trains/{train_number}/timetable/{date}",
        headers={
            'x-api-key': os.getenv("CP_TRAVEL_API_KEY"),
            'x-cp-connect-id': os.getenv("CP_TRAVEL_CONNECT_ID"),
            'x-cp-connect-secret': os.getenv("CP_TRAVEL_CONNECT_SECRET"),
            'User-Agent': os.getenv("USER_AGENT", "cp-gtfs-enhanced/1.0")
        }
    )
    res.raise_for_status()
    return res.json()

def get_trip_shape(trip_id, max_retries=3):
    print(f"Fetching shape for trip: {trip_id}")
    for attempt in range(max_retries):
        try:
            res = requests.get(CP_GIS_API_URL.format(trip_short_name=trip_id), headers={
                'x-api-key': os.getenv("CP_GIS_API_KEY"),
                'x-cp-connect-id': os.getenv("CP_GIS_CONNECT_ID"),
                'x-cp-connect-secret': os.getenv("CP_GIS_CONNECT_SECRET"),
                'User-Agent': os.getenv("USER_AGENT", "cp-gtfs-enhanced/1.0")
            }, timeout=30)
            if res.status_code != 200:
                return None
            return res.json()
        except requests.exceptions.RequestException as e:
            print(f"  Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                print("  Retrying...")
                sleep(2)
            else:
                print(f"  Failed to fetch shape for trip {trip_id} after {max_retries} attempts")
                return None


def enhance_stops(stops_txt):
    """Add platform_code column to stops.txt content."""
    lines = stops_txt.strip().split('\n')
    if not lines:
        return stops_txt
    
    # Add platform_code to header
    header = lines[0]
    new_header = header + ',platform_code'
    
    # Add empty platform_code to each data row
    new_lines = [new_header]
    for line in lines[1:]:
        new_lines.append(line + ',')
    
    return '\n'.join(new_lines)


tz = ZoneInfo("Europe/Madrid")
today = datetime.now(tz).date()

def run():
    print("Downloading GTFS feed...")
    gtfs_zip = get_gtfs_zip(GTFS_ZIP_PATH, GTFS_URL)

    stops_txt = gtfs_zip.read('stops.txt').decode('utf-8')
    stops = list(csv.DictReader(io.StringIO(stops_txt)))
    stops.extend(MISSING_INTERNATIONAL_STOPS)

    trips_txt = gtfs_zip.read('trips.txt').decode('utf-8')
    trips = list(csv.DictReader(io.StringIO(trips_txt)))

    stop_times_txt = gtfs_zip.read('stop_times.txt').decode('utf-8')
    stop_times = list(csv.DictReader(io.StringIO(stop_times_txt)))

    routes_txt = gtfs_zip.read('routes.txt').decode('utf-8')
    routes = list(csv.DictReader(io.StringIO(routes_txt)))

    stations_platforms = {}
    trips_platforms = {}
    # Dict keyed by shape JSON string -> {'trips': [...], 'shape': shape_data}
    keyed_shapes = {}

    # add missing route colors
    for route in routes:
        new_color = MISSING_ROUTE_SERVICE_COLORS.get(route['route_short_name'])[1:] if route['route_short_name'] in MISSING_ROUTE_SERVICE_COLORS else None
        route['route_color'] = new_color if new_color else 'FFFFFF'
        route['route_text_color'] = 'FFFFFF' if new_color else '000000'

    # add fixed stop names
    for stop in stops:
        stop['stop_name'] = get_fixed_name(stop['stop_name'])

    # process international trips to add missing border stations and platforms based on ADIF circulation data
    international_trips_spain = []
    for trip in trips:
        [_, origin_stop_id, destination_stop_id] = trip["route_id"].split("-")

        if origin_stop_id.startswith("71_") or destination_stop_id.startswith("71_"):
            international_trips_spain.append(trip)
            is_origin_spanish = origin_stop_id.startswith("71_")
            spanish_station_id = origin_stop_id if is_origin_spanish else destination_stop_id

            print(f"Processing international trip {trip['trip_short_name']} with Spanish station {spanish_station_id}")

            adif_info = get_adif_circulation(trip["trip_short_name"].rjust(5, '0'))

            # usually returns 2 (today and tomorrow), if any steps are pending means the train hasn't departed yet
            # pending steps will typically only be on spanish stops since adif only has that context on the stops they manage
            adif_next_circulation = next(
                (
                    p for p in adif_info.get("commercialPaths", [])
                    if any(
                        (
                            (s.get("arrivalPassthroughStepSides") and s["arrivalPassthroughStepSides"].get("circulationState") == "PENDING_TO_CIRCULATE")
                            or
                            (s.get("departurePassthroughStepSides") and s["departurePassthroughStepSides"].get("circulationState") == "PENDING_TO_CIRCULATE")
                        )
                        for s in p.get("passthroughSteps", [])
                    )
                ),
                None
            )

            if not adif_next_circulation:
                print(f"  No ADIF circulation found for trip {trip['trip_short_name']} launching on {today}")
                continue

            print(f"  Found ADIF circulation for trip {trip['trip_short_name']} launching on {today}, {adif_next_circulation['commercialPathInfo']['commercialPathKey']['commercialCirculationKey']['commercialNumber']}")

            # 37610 is "Limite Adif BA" which is a theoretical stop representing the border crossing point ig
            # only 485 was verified ending at 37610 for now
            if adif_next_circulation['commercialPathInfo']['commercialDestinationStationCode'] == '37610':
                len_before = len(adif_next_circulation['passthroughSteps'])
                # hardcode transform last stop (37612) into regular badajoz (37606)
                adif_next_circulation['passthroughSteps'][len_before - 1]['stationCode'] = spanish_station_id[3:]
                adif_next_circulation['passthroughSteps'][len_before - 1]['stopType'] = 'COMMERCIAL'
                # hardcoded 5 since that seems to be the usual for now
                adif_next_circulation['passthroughSteps'][len_before - 1]['arrivalPassthroughStepSides']['plannedPlatform'] = stations_platforms.get(spanish_station_id, {4}).pop()


            stations_platforms[spanish_station_id] = set()
            for step in adif_next_circulation["passthroughSteps"]:
                if step["stationCode"] == spanish_station_id[3:]:
                    platform = step['departurePassthroughStepSides']['plannedPlatform'] if is_origin_spanish else step['arrivalPassthroughStepSides']['plannedPlatform']
                    if platform:
                        stations_platforms[spanish_station_id].add(int(platform))
                        trips_platforms[trip['trip_short_name']] = {spanish_station_id.replace("_", "-"): platform}
                        print(f"  Found platform {platform} for trip {trip['trip_short_name']} at station {spanish_station_id}")
                    else:
                        print(f"  No platform info for trip {trip['trip_short_name']} at station {spanish_station_id}")
                    
                    # as per spec, should be in the time zone specified by agency.agency_timezone, not stops.stop_timezone
                    time = get_gtfs_time_from_utc_millis(step['departurePassthroughStepSides']['plannedTime'] if is_origin_spanish else step['arrivalPassthroughStepSides']['plannedTime'])

                    # find all positions for this trip
                    indices = [
                        i for i, s in enumerate(stop_times)
                        if s['trip_id'] == trip['trip_id']
                    ]

                    new_stop = {
                        'trip_id': trip['trip_id'],
                        'arrival_time': time,
                        'departure_time': time,
                        'stop_id': spanish_station_id,
                        # 'stop_sequence': '0' if is_origin_spanish else len([
                        #     c for c in adif_next_circulation["passthroughSteps"]
                        #     if c['stopType'] == 'COMMERCIAL'
                        # ]),
                        'stop_sequence': '0' if is_origin_spanish else str(len(indices)),
                        'pickup_type': '0',
                        'drop_off_type': '0',
                    }


                    if is_origin_spanish:
                        # insert before first occurrence
                        if indices:
                            idx = indices[0]
                        else:
                            idx = len(stop_times)  # no existing stops -> just append
                    else:
                        # insert after last occurrence
                        if indices:
                            idx = indices[-1] + 1
                        else:
                            idx = len(stop_times)

                    stop_times.insert(idx, new_stop)

                    # update stop_sequence for subsequent stops in the same trip
                    # this is not needed because cp leaves out the international stop but it counts towards the stop_sequence
                    # if is_origin_spanish:
                    #     for stop_time in stop_times:
                    #         if stop_time['trip_id'] == trip['trip_id']:
                    #             stop_time['stop_sequence'] = str(int(stop_time['stop_sequence']) + 1)
                    break

    output_path_international = write_gtfs_zip(
        OUTPUT_DIR,
        "cp_gtfs_international.zip",
        gtfs_zip,
        overrides={
            "routes.txt": routes,
            "stops.txt": stops,
            "stop_times.txt": stop_times,
        }
    )

    print(f"international gtfs saved to: {output_path_international}")

    MAX_TRIPS = 30
    # all_trips_details = get_trip_details([int(trip['trip_short_name']) for trip in trips[:MAX_TRIPS]])
    all_trips_details = get_trip_details([int(trip['trip_short_name']) for trip in trips])

    processed_trips = 0

    for trip_short_name, details in all_trips_details.items():
        if details['platforms']:
            if trip_short_name not in trips_platforms:
                trips_platforms[trip_short_name] = details['platforms']
            else:
                trips_platforms[trip_short_name].update(details['platforms'])
            for stop_id, platform in details['platforms'].items():
                if platform != '' and platform is not None:
                    stop_id = stop_id.replace("-", "_")
                    if stop_id not in stations_platforms:
                        stations_platforms[stop_id] = set()
                    stations_platforms[stop_id].add(int(platform))

        if not is_gha:
            print(f"Processing trip {processed_trips + 1}/{len(all_trips_details)}: {trip_short_name}")
            shape = get_trip_shape(trip_short_name)
            if shape is not None:
                shape_key = json.dumps(shape, sort_keys=True)
                if shape_key in keyed_shapes:
                    keyed_shapes[shape_key]['trips'].append(trip_short_name)
                else:
                    keyed_shapes[shape_key] = {'trips': [trip_short_name], 'shape': shape}
            # sleep(2)  # to avoid hitting API rate limits
            processed_trips += 1
    # Convert back to list of tuples if needed: [(trips_list, shape), ...]
    # trips_shapes = [(data['trips'], data['shape']) for data in shapes_dict.values()]

    for idx, stop in enumerate(stops):
        stop_id = stop['stop_id']
        if stop_id in stations_platforms:
            stop['location_type'] = '1'  # indicate it's a station
            for platform in sorted(stations_platforms[stop_id], reverse=True):
                stops.insert(idx + 1,{
                    'stop_id': f'{stop_id}_{platform}',
                    'stop_name': f"{stop['stop_name']} - Linha {platform}",
                    'stop_lat': stop['stop_lat'],
                    'stop_lon': stop['stop_lon'],
                    'location_type': '0',
                    'parent_station': stop_id,
                    'wheelchair_boarding': stop.get('wheelchair_boarding', '0')
                })
            # generic stop for trips where platforms are unknown, since the stop in stop_times must be of location_type 0
            stops.insert(idx + 1,{
                'stop_id': f"{stop_id}_0",
                'stop_name': stop['stop_name'],
                'stop_lat': stop['stop_lat'],
                'stop_lon': stop['stop_lon'],
                'location_type': '0',
                'parent_station': stop_id,
                'wheelchair_boarding': stop.get('wheelchair_boarding', '0')
            })
        else:
            if len(stop_id.split("_")) == 2:
                stop['location_type'] = '1'  # indicate it's a station
                # generic stop for trips where platforms are unknown, since the stop in stop_times must be of location_type 0
                stops.insert(idx + 1,{
                    'stop_id': f"{stop_id}_0",
                    'stop_name': stop['stop_name'],
                    'stop_lat': stop['stop_lat'],
                    'stop_lon': stop['stop_lon'],
                    'location_type': '0',
                    'parent_station': stop_id,
                    'wheelchair_boarding': stop.get('wheelchair_boarding', '0')
                })
    
    # with open('enhanced_stops.txt', 'w', encoding='utf-8', newline='') as f:
    #     writer = csv.DictWriter(f, fieldnames=stops[0].keys())
    #     writer.writeheader()
    #     writer.writerows(stops)

    for idx, stop_time in enumerate(stop_times):
        stop_time['arrival_time'] = normalize_gtfs_time(stop_time['arrival_time'])
        stop_time['departure_time'] = normalize_gtfs_time(stop_time['departure_time'])
        
        stop_id = stop_time['stop_id'].replace("_", "-")
        trip_short_name = stop_time['trip_id'].split('_')[0]
        if trip_short_name in trips_platforms:
            if stop_id in trips_platforms[trip_short_name]:
                platform = trips_platforms[trip_short_name].get(stop_id)
                if platform:
                    stop_id = stop_id.replace("-", "_")
                    stop_time['stop_id'] = f"{stop_id}_{platform}"
                else:
                    stop_id = stop_id.replace("-", "_")
                    stop_time['stop_id'] = f"{stop_id}_0"
        else:
            stop_id = stop_id.replace("-", "_")
            stop_time['stop_id'] = f"{stop_id}_0"


    # if is_gha:
    #     trip_shapes = json.load(open('./preprocessed/trip_shapes.json', 'r'))
    #     for trip in trips:
    #         trip_short_name = trip['trip_short_name']
    #         if trip_short_name in trip_shapes:
    #             trip['shape_id'] = trip_shapes[trip_short_name]
    # else:
    #     shapes_rows = []
    #     for idx, (shape_key, shape_data) in enumerate(keyed_shapes.items()):
    #         for pt_idx, point in enumerate(shape_data['shape']['features'][0]['geometry']['coordinates']):
    #             shapes_rows.append({
    #                 'shape_id': f'shp_{idx}',
    #                 'shape_pt_lat': point[1],
    #                 'shape_pt_lon': point[0],
    #                 'shape_pt_sequence': pt_idx
    #             })

    #     for trip in trips:
    #         trip_short_name = trip['trip_short_name']
    #         for shape_key, shape_data in keyed_shapes.items():
    #             if trip_short_name in shape_data['trips']:
    #                 trip['shape_id'] = f'shp_{list(keyed_shapes.keys()).index(shape_key)}'
    #                 break   

    # with open('enhanced_stop_times.txt', 'w', encoding='utf-8', newline='') as f:
    #     writer = csv.DictWriter(f, fieldnames=stop_times[0].keys())
    #     writer.writeheader()
    #     writer.writerows(stop_times)


         
            
    # Read stops.txt
    # with gtfs_zip.open('stops.txt') as f:
    #     stops_txt = f.read().decode('utf-8')
    
    # # Enhance stops with platform_code column
    # enhanced_stops = enhance_stops(stops_txt)
    
    # print("Enhanced stops.txt with platform_code column")
    # print(f"Preview (first 5 lines):")
    # for line in enhanced_stops.split('\n')[:5]:
    #     print(f"  {line}")
    
    # return enhanced_stops
    
    output_path = write_gtfs_zip(
        OUTPUT_DIR,
        "cp_gtfs_enhanced.zip",
        gtfs_zip,
        overrides={
            "routes.txt": routes,
            "stops.txt": stops,
            "stop_times.txt": stop_times,
            # then we'll add back shapes/trips if re-enabled later
        }
    )
    
    print(f"enhanced gtfs saved to: {output_path}")

run()