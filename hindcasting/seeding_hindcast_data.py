"""
sedd data here
"""

from __future__ import annotations

import json

#set paths

WIND_RESPONSE_PATH = "hindcasting/wind_raw.json"
CURRENT_RESPONSE_PATH = "hindcasting/current_raw.json"
OUTPUT_PATH = "hindcasting/hindcast_data.json"

NUM_RECORDS = 14
SOURCE_LABEL = "cached_live_sample"


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _evenly_spaced_indices(length: int, count: int) -> list[int]:
    """picke on even points not one sided"""
    if count >= length:
        return list(range(length))
    step = (length - 1) / (count - 1)
    return sorted({round(i * step) for i in range(count)})


def build_seed_records(
    wind_path: str,
    current_path: str,
    num_records: int,
) -> list[dict]:
    wind = _load(wind_path)
    current = _load(current_path)

    wind_units = wind["hourly_units"]
    current_units = current["hourly_units"]
    assert wind_units["wind_speed_10m"] == "km/h", (
        f"Expected wind speed in km/h, got {wind_units['wind_speed_10m']} - "
        "conversion needed before using this script as-is"
    )
    assert current_units["ocean_current_velocity"] == "km/h", (
        f"Expected current speed in km/h, got {current_units['ocean_current_velocity']} - "
        "conversion needed before using this script as-is"
    )

    wind_times = wind["hourly"]["time"]
    current_times = current["hourly"]["time"]

    for label, times, series_names in [
        ("wind", wind_times, ["wind_speed_10m", "wind_direction_10m"]),
        ("current", current_times, ["ocean_current_velocity", "ocean_current_direction"]),
    ]:
        source = wind if label == "wind" else current
        for name in series_names:
            series_len = len(source["hourly"][name])
            if series_len != len(times):
                raise ValueError(
                    f"{label} response is inconsistent: 'time' has {len(times)} "
                    f"entries but '{name}' has {series_len} - re-check the saved "
                    f"API response, it may be truncated."
                )

    current_by_time = {
        t: i for i, t in enumerate(current_times)
    }
    common_times = [t for t in wind_times if t in current_by_time]

    if len(common_times) < num_records:
        raise ValueError(
            f"Only {len(common_times)} overlapping timestamps between the "
            f"two files - need at least {num_records}. Re-fetch with a "
            f"wider/matching hourly range."
        )

    indices = _evenly_spaced_indices(len(common_times), num_records)

    rep_lat = round((wind["latitude"] + current["latitude"]) / 2, 4)
    rep_lon = round((wind["longitude"] + current["longitude"]) / 2, 4)

    records = []
    for idx in indices:
        t = common_times[idx]
        w_idx = wind_times.index(t)
        c_idx = current_by_time[t]

        records.append({
            "lat": rep_lat,
            "lon": rep_lon,
            "data_timestamp": t + ":00Z",  # normalize to full ISO8601 with seconds+UTC
            "current": {
                "speed_kmh": current["hourly"]["ocean_current_velocity"][c_idx],
                "direction_deg": current["hourly"]["ocean_current_direction"][c_idx],
            },
            "wind": {
                "speed_kmh": wind["hourly"]["wind_speed_10m"][w_idx],
                "direction_deg": wind["hourly"]["wind_direction_10m"][w_idx],
            },
            "source": SOURCE_LABEL,
        })

    return records


def main():
    records = build_seed_records(WIND_RESPONSE_PATH, CURRENT_RESPONSE_PATH, NUM_RECORDS)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    print(f"Wrote {len(records)} records -> {OUTPUT_PATH}")
    print("First record:")
    print(json.dumps(records[0], indent=2))


if __name__ == "__main__":
    main()