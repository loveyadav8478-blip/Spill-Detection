import pandas as pd

def normalize_input_to_dataset_bounds(input_data, df_ais: pd.DataFrame):
    if df_ais.empty:
        return input_data

    # Ensure datetime parsing is uniform
    df_ais["BaseDateTime"] = pd.to_datetime(df_ais["BaseDateTime"])
    
    # Pick the timestamp of a real ping from a dense part of the dataset (e.g., index 1000)
    sample_index = min(1000, len(df_ais) - 1)
    target_row = df_ais.iloc[sample_index]

    target_time = target_row["BaseDateTime"]
    target_lat = target_row["LAT"]
    target_lon = target_row["LON"]

    # Compute deltas from the incoming origin estimate
    origin_t = pd.to_datetime(input_data.origin_estimate.t)
    if origin_t.tzinfo is not None:
        origin_t = origin_t.tz_localize(None)

    if target_time.tzinfo is not None:
        target_time = target_time.tz_localize(None)

    time_delta = target_time - origin_t
    lat_delta = target_lat - input_data.origin_estimate.lat
    lon_delta = target_lon - input_data.origin_estimate.lon

    # Apply shifts
    input_data.origin_estimate.lat += lat_delta
    input_data.origin_estimate.lon += lon_delta
    input_data.origin_estimate.t = (origin_t + time_delta).to_pydatetime()

    for pt in input_data.backward_path:
        pt.lat += lat_delta
        pt.lon += lon_delta
        
        pt_t = pd.to_datetime(pt.t)
        if pt_t.tzinfo is not None:
            pt_t = pt_t.tz_localize(None)
            
        pt.t = (pt_t + time_delta).to_pydatetime()

    return input_data