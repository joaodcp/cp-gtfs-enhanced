STATION_NAMES_REPLACES = {}

def get_fixed_station_name(name: str) -> str:
    return STATION_NAMES_REPLACES.get(name, name)