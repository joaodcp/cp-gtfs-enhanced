# CP GTFS Enhanced

This project is designed to run on GitHub actions, once every day if changes to the source GTFS feed are detected.
The feed is then enhanced with shapes and platform codes, extracted from CP APIs.

You can access a non-official realtime feed here:

- https://cp-gtfsrt.jdcp.workers.dev/pb (that works with their untouched feed)
- https://cp-gtfsrt.jdcp.workers.dev/pb?includes=platforms (that works with the enhanced versions released here)
