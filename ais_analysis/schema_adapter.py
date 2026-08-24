import json

import pandas as pd

from data.schemas import (
    AISPing,
    TimedPoint,
    FilteredVessel,
    ScoredVessel,
    AISFilterOutput,
    AISScoreOutput,
    AnomalyFlags,
    ScoringWeights
)


def ais_pings_to_dataframe(
    pings: list[AISPing]
) -> pd.DataFrame:
    """
    Convert schema AISPing objects into the same
    DataFrame format expected by the existing
    AIS analysis logic.
    """

    rows = []

    for ping in pings:

        rows.append({
            "MMSI": ping.mmsi,
            "BaseDateTime": ping.base_date_time,
            "LAT": ping.lat,
            "LON": ping.lon,
            "SOG": ping.sog,
            "COG": ping.cog,
            "Heading": ping.heading,
            "VesselName": ping.vessel_name,
            "IMO": ping.imo,
            "CallSign": ping.call_sign,
            "VesselType": ping.vessel_type,
            "Status": ping.status,
            "Length": ping.length,
            "Width": ping.width,
            "Draft": ping.draft,
            "Cargo": ping.cargo,
            "TransceiverClass": ping.transceiver_class
        })

    return pd.DataFrame(rows)


def dataframe_to_filtered_vessels(
    df: pd.DataFrame
) -> list[FilteredVessel]:
    """
    Convert filtered AIS DataFrame into
    FilteredVessel schema objects.
    """

    vessels = []

    if df.empty:
        return vessels

    for mmsi, group in df.groupby("MMSI"):

        trajectory_points = []

        for _, row in group.iterrows():

            trajectory_points.append(
                TimedPoint(
                    lat=float(row["LAT"]),
                    lon=float(row["LON"]),
                    timestamp=row["BaseDateTime"]
                )
            )

        vessels.append(
            FilteredVessel(
                mmsi=str(mmsi),
                trajectory_points=trajectory_points,
                passed_coarse_filter=True,

                # Current AIS logic does not use
                # backward_path yet.
                passed_trajectory_filter=False
            )
        )

    return vessels


def get_vessel_metadata(
    df: pd.DataFrame,
    mmsi: str
) -> dict:
    """
    Extract vessel metadata from the existing
    filtered AIS DataFrame.
    """

    vessel_rows = df[
        df["MMSI"].astype(str) == str(mmsi)
    ]

    if vessel_rows.empty:
        return {}

    row = vessel_rows.iloc[0]

    def optional_value(column):
        if column not in row.index:
            return None

        value = row[column]

        if pd.isna(value):
            return None

        return value

    return {
        "vessel_name": optional_value(
            "VesselName"
        ),
        "imo": optional_value("IMO"),
        "call_sign": optional_value(
            "CallSign"
        ),
        "vessel_type": optional_value(
            "VesselType"
        ),
        "length": optional_value("Length"),
        "width": optional_value("Width")
    }


def ranked_dataframe_to_scored_vessels(
    ranked_df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    origin_estimate: TimedPoint
) -> list[ScoredVessel]:
    """
    Convert the output of the existing
    candidate_ranking.py logic into ScoredVessel.

    Existing ranking logic is NOT changed.
    The existing component scores are mapped
    into the schema response.
    """

    scored_vessels = []

    for _, row in ranked_df.iterrows():

        mmsi = str(row["MMSI"])

        vessel_df = filtered_df[
            filtered_df["MMSI"].astype(str)
            == mmsi
        ].sort_values(
            "BaseDateTime"
        )

        trajectory_points = []

        for _, ping in vessel_df.iterrows():

            trajectory_points.append(
                TimedPoint(
                    lat=float(ping["LAT"]),
                    lon=float(ping["LON"]),
                    timestamp=ping["BaseDateTime"]
                )
            )

        metadata = get_vessel_metadata(
            filtered_df,
            mmsi
        )

        # Calculate time difference using the
        # existing vessel data.
        if not vessel_df.empty:

            first_seen = pd.to_datetime(
                vessel_df[
                    "BaseDateTime"
                ].min()
            )

            origin_time = pd.to_datetime(
                origin_estimate.timestamp
            )

            time_delta_minutes = abs(
                (
                    first_seen
                    - origin_time
                ).total_seconds()
                / 60
            )

        else:
            time_delta_minutes = 0.0

        # Compatibility mapping:
        #
        # Existing AIS logic:
        # distance_score
        # presence_score
        # avg_distance_score
        #
        # These values are exposed through the
        # new schema without changing the
        # original ranking algorithm.

        anomaly = AnomalyFlags(
            ais_gap_detected=False,
            gap_duration_min=0.0,

            speed_deviation_score=0.0,
            course_deviation_score=0.0,

            loitering_detected=False
        )

        explanation = [
            (
                f"Minimum distance to spill: "
                f"{float(row['min_distance_km']):.2f} km"
            ),
            (
                f"Average distance to spill: "
                f"{float(row['avg_distance_km']):.2f} km"
            ),
            (
                f"AIS records near spill: "
                f"{int(row['records'])}"
            ),
            (
                f"Existing candidate confidence: "
                f"{float(row['confidence']):.2f}%"
            )
        ]

        scored_vessels.append(
            ScoredVessel(
                mmsi=mmsi,

                vessel_name=metadata.get(
                    "vessel_name"
                ),
                imo=metadata.get("imo"),
                call_sign=metadata.get(
                    "call_sign"
                ),
                vessel_type=metadata.get(
                    "vessel_type"
                ),
                length=metadata.get("length"),
                width=metadata.get("width"),

                trajectory_points=trajectory_points,

                min_distance_to_origin_km=float(
                    row["min_distance_km"]
                ),

                time_delta_to_origin_min=float(
                    time_delta_minutes
                ),

                anomaly=anomaly,

                # Existing logic mapping
                proximity_score=float(
                    row["distance_score"]
                ),

                temporal_score=float(
                    row["presence_score"]
                ),

                # No trajectory scoring in the
                # current AIS algorithm.
                trajectory_score=0.0,

                behavior_score=float(
                    row["avg_distance_score"]
                ),

                # Existing confidence is 0-100.
                # Unit expects 0-1.
                final_suspect_score=float(
                    row["confidence"]
                ) / 100,

                rank=int(row["rank"]),

                explanation=explanation,

                weights_used=ScoringWeights()
            )
        )

    return scored_vessels


def build_filter_output(
    spill_id: str,
    filtered_df: pd.DataFrame
) -> AISFilterOutput:
    """
    Build AISFilterOutput.
    """

    candidate_vessels = (
        dataframe_to_filtered_vessels(
            filtered_df
        )
    )

    return AISFilterOutput(
        spill_id=spill_id,
        candidate_vessels=candidate_vessels
    )


def build_score_output(
    spill_id: str,
    ranked_df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    origin_estimate: TimedPoint
) -> AISScoreOutput:
    """
    Build AISScoreOutput.
    """

    ranked_vessels = (
        ranked_dataframe_to_scored_vessels(
            ranked_df=ranked_df,
            filtered_df=filtered_df,
            origin_estimate=origin_estimate
        )
    )

    return AISScoreOutput(
        spill_id=spill_id,
        ranked_vessels=ranked_vessels
    )