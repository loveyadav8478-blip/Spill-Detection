import pandas as pd


# Rank vessels based on -> Minimum distance to spill, Average distance to spill 
# and Number of AIS records near the spill

# Returns the top candidate vessels with confidence scores.

def rank_candidate_vessels(
    df: pd.DataFrame,
    top_n: int = 4
):

    # Handle empty DataFrame
    if df.empty:
        return pd.DataFrame(
            columns=[
                "MMSI",
                "records",
                "min_distance_km",
                "avg_distance_km",
                "first_seen",
                "last_seen",
                "distance_score",
                "presence_score",
                "avg_distance_score",
                "confidence",
                "rank"
            ]
        )

    # Summarize each vessel
    vessel_summary = (
        df.groupby("MMSI")
        .agg(
            records=("MMSI", "size"),
            min_distance_km=(
                "distance_to_spill_km",
                "min"
            ),
            avg_distance_km=(
                "distance_to_spill_km",
                "mean"
            ),
            first_seen=(
                "BaseDateTime",
                "min"
            ),
            last_seen=(
                "BaseDateTime",
                "max"
            )
        )
        .reset_index()
    )

    # Score based on minimum distance
    max_min_distance = vessel_summary[
        "min_distance_km"
    ].max()

    if max_min_distance == 0:
        vessel_summary["distance_score"] = 1.0
    else:
        vessel_summary["distance_score"] = (
            1
            - vessel_summary["min_distance_km"]
            / max_min_distance
        )

    # Score based on presence / number of records
    max_records = vessel_summary["records"].max()

    if max_records == 0:
        vessel_summary["presence_score"] = 0.0
    else:
        vessel_summary["presence_score"] = (
            vessel_summary["records"]
            / max_records
        )

    # Score based on average distance
    max_avg_distance = vessel_summary[
        "avg_distance_km"
    ].max()

    if max_avg_distance == 0:
        vessel_summary["avg_distance_score"] = 1.0
    else:
        vessel_summary["avg_distance_score"] = (
            1
            - vessel_summary["avg_distance_km"]
            / max_avg_distance
        )

    # Final confidence score
    vessel_summary["confidence"] = (
        0.4 * vessel_summary["distance_score"]
        + 0.3 * vessel_summary["presence_score"]
        + 0.3 * vessel_summary["avg_distance_score"]
    ) * 100

    # Sort by confidence
    ranked_vessels = (
        vessel_summary
        .sort_values(
            "confidence",
            ascending=False
        )
        .head(top_n)
        .reset_index(drop=True)
    )

    # Add ranking
    ranked_vessels["rank"] = (
        ranked_vessels.index + 1
    )

    return ranked_vessels