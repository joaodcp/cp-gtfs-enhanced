from time import sleep
import requests
import zipfile
import io
import csv
import json
import os
from datetime import datetime

is_gha = os.getenv("GITHUB_ACTIONS") == "true"

GTFS_URL = "https://publico.cp.pt/gtfs/gtfs.zip"
OUTPUT_DIR = "./enhanced"
CP_GIS_API_URL = "https://api-gateway.cp.pt/cp/services/gis-api/train-path/{trip_short_name}"

def get_gtfs_zip():
    response = requests.get(GTFS_URL, stream=True, timeout=30)
    response.raise_for_status()
    return zipfile.ZipFile(io.BytesIO(response.content))

def get_station_arrivals(station_id, date, start_time):
    res = requests.get(
        f"https://api-gateway.cp.pt/cp/services/travel-api/stations/{station_id}/timetable/{date}?start={start_time}",
        headers={
            'x-api-key': 'ca3923e4-1d3c-424f-a3d0-9554cf3ef859',
            'x-cp-connect-id': '1483ea620b920be6328dcf89e808937a',
            'x-cp-connect-secret': '74bd06d5a2715c64c2f848c5cdb56e6b'
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
            'x-api-key': '5abe3d05-c76e-11cc-8ff1-cdc14135bb6f',
            'x-cp-connect-id': 'edc64b3e659cfecf2f4e154dc6cef3c7',
            'x-cp-connect-secret': '0bf2222674b8a419c8afe426d8a70465'
        }
    )
    res.raise_for_status()
    return res.json()

def get_trip_shape(trip_id, max_retries=3):
    print(f"Fetching shape for trip: {trip_id}")
    for attempt in range(max_retries):
        try:
            res = requests.get(CP_GIS_API_URL.format(trip_short_name=trip_id), headers={
                'x-api-key': '8a208a6c-03e8-41f4-a39a-cec47cd7b446',
                'x-cp-connect-id': 'edc64b3e659cfecf2f4e154dc6cef3c7',
                'x-cp-connect-secret': '0bf2222674b8a419c8afe426d8a70465'
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


def run():
    print("Downloading GTFS feed...")
    gtfs_zip = get_gtfs_zip()

    stops_txt = gtfs_zip.read('stops.txt').decode('utf-8')
    stops = list(csv.DictReader(io.StringIO(stops_txt)))

    trips_txt = gtfs_zip.read('trips.txt').decode('utf-8')
    trips = list(csv.DictReader(io.StringIO(trips_txt)))

    stop_times_txt = gtfs_zip.read('stop_times.txt').decode('utf-8')
    stop_times = list(csv.DictReader(io.StringIO(stop_times_txt)))

    stations_platforms = {}
    trips_platforms = {}
    # Dict keyed by shape JSON string -> {'trips': [...], 'shape': shape_data}
    keyed_shapes = {}

    MAX_TRIPS = 30
    # all_trips_details = get_trip_details([int(trip['trip_short_name']) for trip in trips[:MAX_TRIPS]])
    all_trips_details = get_trip_details([int(trip['trip_short_name']) for trip in trips])

    processed_trips = 0

    for trip_short_name, details in all_trips_details.items():
        if details['platforms']:
            trips_platforms[trip_short_name] = details['platforms']
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
        stop_time['arrival_time'] = normalize_gtfs_time(stop_time['arrival_time']
        stop_time['departure_time'] = normalize_gtfs_time(stop_time['departure_time']
        
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


    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"cp_gtfs_enhanced.zip"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    print(f"creating enhanced gtfs package at {output_path}...")
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as enhanced_zip:
        stops_output = io.StringIO()
        writer = csv.DictWriter(stops_output, fieldnames=stops[0].keys())
        writer.writeheader()
        writer.writerows(stops)
        enhanced_zip.writestr('stops.txt', stops_output.getvalue())
        print("wrote enhanced stops.txt")
        
        stop_times_output = io.StringIO()
        writer = csv.DictWriter(stop_times_output, fieldnames=stop_times[0].keys())
        writer.writeheader()
        writer.writerows(stop_times)
        enhanced_zip.writestr('stop_times.txt', stop_times_output.getvalue())
        print("wrote enhanced stop_times.txt")

        # if is_gha:
        #     with open('./preprocessed/shapes.txt', 'r', encoding='utf-8') as f:
        #         enhanced_zip.writestr('shapes.txt', f.read())
        #     print("wrote preprocessed shapes.txt")
        # else:
        #     shapes_output = io.StringIO()
        #     writer = csv.DictWriter(shapes_output, fieldnames=shapes_rows[0].keys())
        #     writer.writeheader()
        #     writer.writerows(shapes_rows)
        #     enhanced_zip.writestr('shapes.txt', shapes_output.getvalue())
        #     print("wrote enhanced shapes.txt")
        
        # trips_output = io.StringIO()
        # writer = csv.DictWriter(trips_output, fieldnames=trips[0].keys())
        # writer.writeheader()
        # writer.writerows(trips)
        # enhanced_zip.writestr('trips.txt', trips_output.getvalue())
        # print("wrote enhanced trips.txt")

        
        # Copy all other files from original GTFS unchanged
        for file_info in gtfs_zip.filelist:
            if file_info.filename not in ['stops.txt', 'stop_times.txt', 'shapes.txt']:
                enhanced_zip.writestr(file_info.filename, gtfs_zip.read(file_info.filename))
                print(f"copied {file_info.filename}")
    
    print(f"enhanced gtfs saved to: {output_path}")
    return output_path

run()