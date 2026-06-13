# CP GTFS Enhanced

This project is designed to run on GitHub actions, once every day if changes to the source GTFS feed are detected.
The feed is then enhanced with shapes and platform codes, extracted from CP APIs.

You can access a non-official realtime feed here:

- https://cp-gtfsrt.jdcp.workers.dev/vehicle-positions/pb
- https://cp-gtfsrt.jdcp.workers.dev/trip-updates/pb

You can add the query param `?includes=platforms` to use the realtime feed with the platform information the enhanced versions released here have.

## Feeds
Three feeds are generated every day:

### cp_gtfs_enhanced.zip
This feed is the one that includes all improvements.

Includes:
- Platform codes
- Shapes
- Spanish station information (Badajoz, Vigo-Guixar)
- Fixed stop names (diacritics, formatting, etc.)

### cp_gtfs_internacional
This feed includes all improvements except the platform codes.

Includes:
- Shapes
- Spanish station information (Badajoz, Vigo-Guixar)
- Fixed stop names (diacritics, formatting, etc.)

### cp_gtfs_grouped
This feed is very different from the original and should used for presentation in apps where a line list is used.

Includes:
- Routes deduped by direction (routes that only differ in direction are collapsed into one)
- Line fields: adds the concept of lines which group multiple similar trip variants
- Patterns: adds the concept of patterns (groups of trips with similar sequences)
- Shapes

This way, instead of displaying a bunch of similar routes in a list, they are grouped into a higher level organizational entity — line.<br>
When viewing line details, there should be a field to select a route variant and, inside the route, a pattern (direction).

Example:
```
line_id: SADO
line_short_name: Sado
line_long_name: Barreiro - Praias do Sado-A
├── route_id: SADO_0
├── route_short_name: Sado
├── route_long_name: Barreiro - Setubal
│   ├── pattern_id: SADO_0_0 (Barreiro to Setúbal)
│   └── pattern_id: SADO_0_1 (Setúbal to Barreiro)
│
├── route_id: SADO_1
├── route_short_name: Sado
└── route_long_name: Barreiro - Praias do Sado-A
    ├── pattern_id: SADO_1_0 (Barreiro to Praias do Sado-A)
    └── pattern_id: SADO_1_1 (Praias do Sado-A to Barreiro)
```

### cp_gtfs_pfaedled
Most of this feed is untouched and is mostly for comparison purposes with the original one.<br>
It only includes the shapes.

Includes:
- Shapes
