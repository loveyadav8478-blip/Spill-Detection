from .ais_loader import load_ais_data
from .time_filter import filter_by_time
from .spatial_filter import filter_by_distance
from .candidate_ranking import rank_candidate_vessels


def run_ais_pipeline(
    ais_file_path: str,
    spill_timestamp,
    spill_lat: float,
    spill_lon: float,
    duration_minutes: int = 60,
    radius_km: float = 34,
    top_n: int = 4
):
    """
    Run the complete AIS vessel candidate detection pipeline.
    """

    # 1. Load AIS data
    df = load_ais_data(ais_file_path)

    # 2. Filter AIS records by time
    time_filtered = filter_by_time(
        df,
        spill_timestamp,
        duration_minutes
    )

    # 3. Filter vessels by distance from spill
    spatial_filtered = filter_by_distance(
        time_filtered,
        spill_lat,
        spill_lon,
        radius_km
    )

    # 4. Rank candidate vessels
    ranked_vessels = rank_candidate_vessels(
        spatial_filtered,
        top_n
    )

    return ranked_vessels