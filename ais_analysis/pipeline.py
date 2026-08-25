from data.schemas import AISFilterInput, AISFilterOutput, AISScoreOutput


from .ais_loader import load_ais_data
from .normalizing_data import normalize_input_to_dataset_bounds
from .time_filter import filter_by_time
from .spatial_filter import filter_by_distance
from .candidate_ranking import rank_candidate_vessels

from .schema_adapter import (
    ais_pings_to_dataframe,
    build_filter_output,
    build_score_output,
)


#  Run the AIS vessel candidate detection pipeline.
# (AIS Pings -> DataFrame -> Time Filter -> Spatial Filter -> Candidate Ranking -> Schema Output)

def run_ais_pipeline(
    input_data: AISFilterInput, top_n: int = 4
) -> tuple[AISFilterOutput, AISScoreOutput]:

    # Convert AISPing schema objects into the same DataFrame format

    df = load_ais_data("data/ais/ais_dataset.csv")
    input_data = normalize_input_to_dataset_bounds(input_data, df)

    if df.empty:

        filter_output = AISFilterOutput(
            spill_id=input_data.spill_id, candidate_vessels=[]
        )

        score_output = AISScoreOutput(spill_id=input_data.spill_id, ranked_vessels=[])

        return (filter_output, score_output)

    # Ensure timestamp format is correct
    df["BaseDateTime"] = df["BaseDateTime"].astype("datetime64[ns]")

    # Get spill location and time from Hindcast
    origin = input_data.origin_estimate

    spill_timestamp = origin.t
    spill_lat = origin.lat
    spill_lon = origin.lon

    # Filtering on the basis of time
    duration_minutes = int(input_data.coarse_time_window_hours * 60)

    time_filtered = filter_by_time(
        df=df, spill_time=spill_timestamp, duration_minutes=duration_minutes
    )

    # Spatial Filtering
    spatial_filtered = filter_by_distance(
        df=time_filtered,
        spill_lat=spill_lat,
        spill_lon=spill_lon,
        radius_km=input_data.coarse_radius_km,
    )

    # Candidate Ranking
    ranked_vessels = rank_candidate_vessels(df=spatial_filtered, top_n=top_n)

    # Convert to schema outputs
    filter_output = build_filter_output(
        spill_id=input_data.spill_id,
        filtered_df=spatial_filtered,
        ranked_df=ranked_vessels,
    )

    score_output = build_score_output(
        spill_id=input_data.spill_id,
        ranked_df=ranked_vessels,
        filtered_df=spatial_filtered,
        origin_estimate=origin,
    )


    return (filter_output, score_output)
