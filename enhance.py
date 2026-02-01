import requests
import zipfile
import io
import csv
import json
import os
from datetime import datetime

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
    print("Fetching trip details for trip IDs:", trip_ids)
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

def get_trip_shape(trip_id):
    res = requests.get(CP_GIS_API_URL.format(trip_short_name=trip_id), headers={
        'x-api-key': '8a208a6c-03e8-41f4-a39a-cec47cd7b446',
        'x-cp-connect-id': 'edc64b3e659cfecf2f4e154dc6cef3c7',
        'x-cp-connect-secret': '0bf2222674b8a419c8afe426d8a70465'
    })
    if res.status_code != 200:
        return None
    return res.json()


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
    shapes_dict = {}

    MAX_TRIPS = 10
    # all_trips_details = get_trip_details([int(trip['trip_short_name']) for trip in trips[:MAX_TRIPS]])
    all_trips_details = get_trip_details([int(trip['trip_short_name']) for trip in trips])

    for trip_short_name, details in all_trips_details.items():
        if details['platforms']:
            trips_platforms[trip_short_name] = details['platforms']
            for stop_id, platform in details['platforms'].items():
                if platform != '' and platform is not None:
                    stop_id = stop_id.replace("-", "_")
                    if stop_id not in stations_platforms:
                        stations_platforms[stop_id] = set()
                    stations_platforms[stop_id].add(int(platform))

        # shape = get_trip_shape(trip_short_name)
        # if shape is not None:
        #     # Use JSON string as key to check for duplicates
        #     shape_key = json.dumps(shape, sort_keys=True)
        #     if shape_key in shapes_dict:
        #         shapes_dict[shape_key]['trips'].append(trip_short_name)
        #     else:
        #         shapes_dict[shape_key] = {'trips': [trip_short_name], 'shape': shape}
    
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
    
    # with open('enhanced_stops.txt', 'w', encoding='utf-8', newline='') as f:
    #     writer = csv.DictWriter(f, fieldnames=stops[0].keys())
    #     writer.writeheader()
    #     writer.writerows(stops)

    for idx, stop_time in enumerate(stop_times):
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
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"cp_gtfs_enhanced_{timestamp}.zip"
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
        
        # Copy all other files from original GTFS unchanged
        for file_info in gtfs_zip.filelist:
            if file_info.filename not in ['stops.txt', 'stop_times.txt']:
                enhanced_zip.writestr(file_info.filename, gtfs_zip.read(file_info.filename))
                print(f"copied {file_info.filename}")
    
    print(f"enhanced gtfs saved to: {output_path}")
    return output_path

run()