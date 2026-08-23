import argparse
import json
import math


EARTH_RADIUS_KM = 6371.0


def destination_point(lat, lon, distance_km, bearing_deg):

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

    direction = math.radians(direction_deg)

    north = speed_kmh * math.cos(direction)
    east = speed_kmh * math.sin(direction)

    return north, east


def calculate_drift(environment):

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

    # Same prototype weighting used by hindcast
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

    direction = (
        math.degrees(
            math.atan2(east, north)
        ) + 360
    ) % 360

    return {
        "northKmh": north,
        "eastKmh": east,
        "speedKmh": speed,
        "directionDeg": direction
    }


def forecast_point(
    latitude,
    longitude,
    drift,
    hours
):

    distance = drift["speedKmh"] * hours

    lat, lon = destination_point(
        latitude,
        longitude,
        distance,
        drift["directionDeg"]
    )

    return {
        "hoursAhead": hours,
        "distanceKm": round(distance, 3),
        "latitude": round(lat, 6),
        "longitude": round(lon, 6)
    }


def run_forecast(
    latitude,
    longitude,
    environment
):

    drift = calculate_drift(environment)

    forecast_hours = [6, 12, 24]

    points = []

    for hours in forecast_hours:

        points.append(
            forecast_point(
                latitude,
                longitude,
                drift,
                hours
            )
        )

    return {

        "currentLocation": {
            "latitude": latitude,
            "longitude": longitude
        },

        "environment": environment,

        "driftVector": drift,

        "forecast": points,

        "model": {
            "type": "prototype_forward_drift",
            "note": (
                "Simplified demonstration model. "
                "Uses constant environmental conditions."
            )
        }

    }


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Oil spill forecast prototype"
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
        "--output",
        default="forecast_result.json"
    )

    args = parser.parse_args()

    with open(
        args.environment,
        "r",
        encoding="utf-8"
    ) as f:

        environment = json.load(f)

    result = run_forecast(
        args.lat,
        args.lon,
        environment
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