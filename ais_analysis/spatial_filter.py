import pandas as pd
import numpy as np


def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2
):
    # Calculate distance between two geographic points in kilometers.

    R = 6371

    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1)
        * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    c = 2 * np.arctan2(
        np.sqrt(a),
        np.sqrt(1 - a)
    )

    return R * c


def filter_by_distance(
    df: pd.DataFrame,
    spill_lat: float,
    spill_lon: float,
    radius_km: float = 34
):

    # Calculate distance of AIS records from the spill and keep records inside the given radius.

    df = df.copy()

    # Calculate distance from spill
    df["distance_to_spill_km"] = haversine_distance(
        df["LAT"],
        df["LON"],
        spill_lat,
        spill_lon
    )

    # Keep vessels within radius
    filtered_df = df[
        df["distance_to_spill_km"] <= radius_km
    ].copy()

    return filtered_df
