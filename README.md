# CP GTFS Enhanced

This project is designed to run on GitHub actions, once every day if changes to the source GTFS feed are detected.
The feed is then enhanced with shapes and platform codes, extracted from CP APIs.

You can access a non-official realtime feed here:

- https://cp-gtfsrt.jdcp.workers.dev/vehicle-positions/pb
- https://cp-gtfsrt.jdcp.workers.dev/trip-updates/pb

You can add the query param includes=platforms to use the realtime feed with the platform information the enhanced versions released here have.
