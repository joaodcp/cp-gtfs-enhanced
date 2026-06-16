import copy
from datetime import datetime

from utils.names import get_fixed_name

PREFER_BA_STOPS_FOR_ROUTE_LONG_NAME = True

LINE_LONG_NAME_REPLACES = {
    "AP": "Lisboa - Norte/Sul",
    "IC": "Intercidades",
    "IR": "Interregionais",
    "R": "Regionais",
    "U": "Urbanos",
    "Linha de Sintra": "Sintra - Lisboa - Azambuja",
    "Linha da Azambuja": "Azambuja - Lisboa - Sintra",
    "Linha de Cascais": "Cascais - Cais do Sodré",
    "Linha do Sado": "Barreiro - Praias do Sado-A",
    "Linha de Aveiro": "Porto São Bento - Aveiro",
    "Linha do Marco": "Porto São Bento - Marco de Canaveses",
    "Linha de Guimaraes": "Porto São Bento - Guimarães",
    "Linha de Braga": "Porto São Bento - Braga",
    "Linha de Leixoes": "Leça do Balio - Porto Campanhã - Ovar",
}


# ----------------------------
# helpers
# ----------------------------

def normalize_line_name(name):
    if not name:
        return name

    for p in ("Linha de ", "Linha da ", "Linha do "):
        if name.startswith(p):
            return get_fixed_name(name.replace(p, ""))
    return name


def build_indexes(feed):
    routes_by_id = {r["route_id"]: r for r in feed["routes"]}
    stops_by_id = {s["stop_id"]: s for s in feed["stops"]}

    stoptimes_by_trip = {}
    for st in feed["stop_times"]:
        stoptimes_by_trip.setdefault(st["trip_id"], []).append(st)

    trips_by_route = {}
    for t in feed["trips"]:
        trips_by_route.setdefault(t["route_id"], []).append(t)

    return routes_by_id, stops_by_id, stoptimes_by_trip, trips_by_route


def get_route_signature(route_id, trips_by_route, stoptimes_by_trip):
    trips = trips_by_route.get(route_id, [])
    if not trips:
        return ()

    best_trip = max(
        trips,
        key=lambda t: len(stoptimes_by_trip.get(t["trip_id"], []))
    )

    stop_times = sorted(
        stoptimes_by_trip.get(best_trip["trip_id"], []),
        key=lambda st: int(st["stop_sequence"])
    )

    return tuple(st["stop_id"] for st in stop_times)


def terminal_pair(route_id, trips_by_route, stoptimes_by_trip):
    sig = get_route_signature(route_id, trips_by_route, stoptimes_by_trip)
    if not sig:
        return ("?", "?")
    return (sig[0], sig[-1])


def build_lines(feed, trips_by_route, stoptimes_by_trip):
    lines = {}

    for r in feed["routes"]:
        rid = r["route_id"]
        short = r.get("route_short_name")
        if not short:
            continue

        line_id = normalize_line_name(short)
        a, b = terminal_pair(rid, trips_by_route, stoptimes_by_trip)

        variant_key = tuple(sorted((a, b)))
        direction = 0 if (a, b) == variant_key else 1

        lines.setdefault(line_id, {"variants": {}, "original_short": short})
        lines[line_id]["variants"].setdefault(variant_key, {0: set(), 1: set()})
        lines[line_id]["variants"][variant_key][direction].add(rid)

    return lines


def build_mappings(lines):
    route_id_to_new = {}
    route_id_to_pattern = {}

    for line_id, line in lines.items():
        variant_index = 0
        line_id_upper = line_id.upper()

        for variant_key, dirs in line["variants"].items():
            for direction_id in (0, 1):
                route_ids = dirs.get(direction_id, set())
                if not route_ids:
                    continue

                new_route_id = f"{line_id_upper}_{variant_index}"
                pattern_id = f"{new_route_id}_{direction_id}"

                for rid in route_ids:
                    route_id_to_new[rid] = new_route_id
                    route_id_to_pattern[rid] = pattern_id

            variant_index += 1

    return route_id_to_new, route_id_to_pattern


# ----------------------------
# main transform
# ----------------------------

import copy

def get_grouped_gtfs(feed, agency_id_replace="3"):
    feed = copy.deepcopy(feed)

    routes_by_id = {r["route_id"]: r for r in feed["routes"]}
    stops_by_id = {s["stop_id"]: s for s in feed["stops"]}

    stoptimes_by_trip = {}
    for st in feed["stop_times"]:
        stoptimes_by_trip.setdefault(st["trip_id"], []).append(st)

    trips_by_route = {}
    for t in feed["trips"]:
        trips_by_route.setdefault(t["route_id"], []).append(t)

    # ----------------------------
    # build structure
    # ----------------------------

    lines = {}

    for r in feed["routes"]:
        rid = r["route_id"]
        short = r.get("route_short_name")

        if not short:
            continue

        line_id = normalize_line_name(short)

        a, b = terminal_pair(
            rid,
            trips_by_route,
            stoptimes_by_trip
        )

        variant_key = tuple(sorted((a, b)))
        direction = 0 if (a, b) == variant_key else 1

        lines.setdefault(line_id, {
            "variants": {},
            "original_short": short
        })

        if variant_key not in lines[line_id]["variants"]:
            lines[line_id]["variants"][variant_key] = {
                0: set(),
                1: set()
            }

        lines[line_id]["variants"][variant_key][direction].add(rid)

    # ----------------------------
    # route mappings
    # ----------------------------

    route_id_to_new = {}
    route_id_to_pattern = {}

    for line_id, line in lines.items():

        variant_index = 0
        line_id_upper = line_id.upper()

        for variant_key, dirs in line["variants"].items():

            for direction_id in (0, 1):

                route_ids = dirs.get(direction_id, set())
                if not route_ids:
                    continue

                new_route_id = f"{line_id_upper}_{variant_index}"
                pattern_id = f"{new_route_id}_{direction_id}"

                for rid in route_ids:
                    route_id_to_new[rid] = new_route_id
                    route_id_to_pattern[rid] = pattern_id

            variant_index += 1

    # ----------------------------
    # rebuild routes
    # ----------------------------

    new_routes = []

    for line_id, line in lines.items():

        line_short_name = line_id
        line_long_name = LINE_LONG_NAME_REPLACES.get(
            line["original_short"],
            ""
        )

        variant_index = 0
        line_id_upper = line_id.upper()

        for variant_key, dirs in line["variants"].items():

            rep_route_id = None

            for d in (0, 1):
                if dirs.get(d):
                    rep_route_id = sorted(dirs[d])[0]
                    break

            rep_route = routes_by_id.get(rep_route_id, {})

            a, b = variant_key

            a_name = stops_by_id.get(a, {}).get("stop_name", a)
            b_name = stops_by_id.get(b, {}).get("stop_name", b)

            route_long_name = (
                f"{b_name} - {a_name}"
                if PREFER_BA_STOPS_FOR_ROUTE_LONG_NAME
                else f"{a_name} - {b_name}"
            )

            new_routes.append({
                "agency_id": agency_id_replace,
                "line_id": line_id_upper,
                "line_short_name": line_short_name,
                "line_long_name": line_long_name,
                "route_id": f"{line_id_upper}_{variant_index}",
                "route_short_name": line_short_name,
                "route_long_name": route_long_name,
                "route_type": rep_route.get("route_type", "2"),
                "route_color": rep_route.get("route_color", "FFFFFF"),
                "route_text_color": rep_route.get(
                    "route_text_color",
                    "000000"
                ),
            })

            variant_index += 1

    feed["routes"] = new_routes

    # ----------------------------
    # rebuild trips
    # ----------------------------

    for trip in feed["trips"]:

        old_rid = trip["route_id"]

        if old_rid in route_id_to_new:
            trip["route_id"] = route_id_to_new[old_rid]

        if old_rid in route_id_to_pattern:
            trip["pattern_id"] = route_id_to_pattern[old_rid]
            trip["direction_id"] = int(
                trip["pattern_id"].rsplit("_", 1)[1]
            )

    return feed