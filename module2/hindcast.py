import argparse
import json
import math
from pathlib import Path


EARTH_RADIUS_KM = 6371.0


def destination_point(lat, lon, distance_km, bearing_deg):
    """
    Move a point along the Earth's surface.

    bearing:
        0   = North
        90  = East
        180 = South
        270 = West
    """

    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    bearing = math.radians(bearing_deg)

    angular_distance = distance_km / EARTH_RADIUS_KM

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        +
        math.cos(lat1)
        * math.sin(angular_distance)
        * math.cos(bearing)
    )

    lon2 = lon1 + math.atan2(
        math.sin(bearing)
        * math.sin(angular_distance)
        * math.cos(lat1),
        math.cos(angular_distance)
        -
        math.sin(lat1) * math.sin(lat2)
    )

    return (
        math.degrees(lat2),
        math.degrees(lon2)
    )


def vector_components(speed_kmh, direction_deg):
    """
    Convert speed + bearing into north/east components.
    """

    direction = math.radians(direction_deg)

    north = speed_kmh * math.cos(direction)
    east = speed_kmh * math.sin(direction)

    return north, east


def combine_environment(environment):
    """
    Combine wind and current into an approximate surface drift vector.

    This is a prototype approximation.
    """

    wind_speed = environment["wind"]["speedKmh"]
    wind_direction = environment["wind"]["directionDeg"]

    current_speed_ms = environment["current"]["speedMs"]
    current_speed_kmh = current_speed_ms * 3.6
    current_direction = environment["current"]["directionDeg"]

    wind_north, wind_east = vector_components(
        wind_speed,
        wind_direction
    )

    current_north, current_east = vector_components(
        current_speed_kmh,
        current_direction
    )

    # Prototype weighting.
    # Later this should be replaced with a calibrated
    # oil-drift model.
    wind_weight = 0.03
    current_weight = 1.0

    north = (
        wind_north * wind_weight
        +
        current_north * current_weight
    )

    east = (
        wind_east * wind_weight
        +
        current_east * current_weight
    )

    speed = math.sqrt(
        north ** 2 +
        east ** 2
    )

    bearing = (
        math.degrees(
            math.atan2(east, north)
        )
        + 360
    ) % 360

    return {
        "northKmh": north,
        "eastKmh": east,
        "speedKmh": speed,
        "directionDeg": bearing
    }


def hindcast(
    latitude,
    longitude,
    environment,
    hours
):
    """
    Reverse the estimated drift for a specified
    number of hours.
    """

    drift = combine_environment(environment)

    reverse_bearing = (
        drift["directionDeg"] + 180
    ) % 360

    distance = (
        drift["speedKmh"] * hours
    )

    origin_lat, origin_lon = destination_point(
        latitude,
        longitude,
        distance,
        reverse_bearing
    )

    return {
        "hoursBack": hours,
        "distanceKm": round(distance, 3),
        "latitude": round(origin_lat, 6),
        "longitude": round(origin_lon, 6)
    }


def run_hindcast(
    latitude,
    longitude,
    environment,
    max_hours
):
    """
    Generate candidate origins at multiple
    historical time steps.
    """

    candidates = []

    for hours in range(1, max_hours + 1):

        candidate = hindcast(
            latitude,
            longitude,
            environment,
            hours
        )

        candidates.append(candidate)

    # Prototype assumption:
    # The origin is the furthest reconstructed point.
    # This will later be replaced by a probability/
    # physics-based origin estimation method.
    estimated_origin = candidates[-1]

    return {
        "observedLocation": {
            "latitude": latitude,
            "longitude": longitude
        },

        "environment": environment,

        "driftVector": combine_environment(
            environment
        ),

        "candidateOrigins": candidates,

        "estimatedOrigin": {
            "latitude": estimated_origin["latitude"],
            "longitude": estimated_origin["longitude"],
            "hoursBack": estimated_origin["hoursBack"],
            "distanceKm": estimated_origin["distanceKm"]
        },

        "confidence": None,

        "model": {
            "type": "prototype_reverse_drift",
            "note": (
                "Simplified demonstration model. "
                "Replace with calibrated oceanographic "
                "hindcast before operational use."
            )
        }
    }


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Oil spill hindcast prototype"
    )

    parser.add_argument(
        "--lat",
        type=float,
        required=True
    )

    parser.add_argument(
        "--lon",
        type=float,
        required=True
    )

    parser.add_argument(
        "--environment",
        required=True
    )

    parser.add_argument(
        "--hours",
        type=int,
        default=6
    )

    parser.add_argument(
        "--output",
        default="hindcast_result.json"
    )

    args = parser.parse_args()

    with open(
        args.environment,
        "r",
        encoding="utf-8"
    ) as f:

        environment = json.load(f)

    result = run_hindcast(
        args.lat,
        args.lon,
        environment,
        args.hours
    )

    with open(
        args.output,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            indent=2
        )

    print(
        json.dumps(
            result,
            indent=2
        )
    )