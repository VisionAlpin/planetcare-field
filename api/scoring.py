from typing import Optional


def compute_field_profile(indicators: list[dict]) -> dict:
    """Compute sustainability scores from indicator values.

    indicators: list of pcf_indicator_values records
    Returns: {score_water, score_biodiversity, score_pesticide, score_total,
              available_dimensions, method_version}
    """
    scores = {}

    # Water Score (W): from NDVI stability + CDI
    ndvi_values = [i for i in indicators if i["indicator"] == "ndvi_mean"]
    cdi_values = [i for i in indicators if i["indicator"] == "cdi"]
    if ndvi_values and cdi_values:
        ndvi_mean = sum(i["value"] for i in ndvi_values) / len(ndvi_values)
        cdi_mean = sum(i["value"] for i in cdi_values) / len(cdi_values)
        # NDVI 0.2–0.8 → normalised 0–100; CDI 0=no stress, 5=extreme → inverted
        w_ndvi = min(100, max(0, (ndvi_mean - 0.2) / 0.6 * 100))
        w_cdi = min(100, max(0, (1 - cdi_mean / 5) * 100))
        scores["score_water"] = round((w_ndvi + w_cdi) / 2, 1)

    # Biodiversity Score (B): from NDVI spatial variability (heterogeneity = good)
    ndvi_std_values = [i for i in indicators if i["indicator"] == "ndvi_std"]
    if ndvi_std_values:
        ndvi_std_mean = sum(i["value"] for i in ndvi_std_values) / len(ndvi_std_values)
        # Std 0.05–0.25 → high variability = higher biodiversity potential
        b_score = min(100, max(0, (ndvi_std_mean - 0.05) / 0.20 * 100))
        scores["score_biodiversity"] = round(b_score, 1)

    # Pesticide Score (P): from manually entered data (Phase 0: optional)
    pest_values = [i for i in indicators if i["indicator"] == "pesticide"]
    if pest_values:
        # value 0 = no pesticides (score 100), 100 = heavy use (score 0)
        p_mean = sum(i["value"] for i in pest_values) / len(pest_values)
        scores["score_pesticide"] = round(max(0, 100 - p_mean), 1)

    # Total: average of available sub-scores (min 2 required)
    available = list(scores.values())
    if len(available) >= 2:
        scores["score_total"] = round(sum(available) / len(available), 1)
    else:
        scores["score_total"] = None

    scores["available_dimensions"] = len(available)
    scores["method_version"] = "1.0"
    return scores
