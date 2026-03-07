"""Weather anomaly detection and trend analysis for Indian cities.

Uses statistical z-scores against 30-year climate normals combined with
IMD-aligned rule-based thresholds to detect heat waves, cold waves,
extreme rainfall, drought signals, and cyclone proxies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from scrapers.weather import CITY_BY_NAME, VARIABLE_TO_COLUMN

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Dataclasses for detected anomalies
# ──────────────────────────────────────────────────────────────────────


@dataclass
class DetectedAnomaly:
    """A single detected weather anomaly event."""
    city: str
    anomaly_type: str  # heat_wave, cold_wave, extreme_rain, drought, cyclone_proxy, unusual_warmth
    severity: str      # warning, severe, extreme
    start_date: date
    end_date: date | None = None
    peak_value: float | None = None
    z_score: float | None = None
    description: str | None = None

    @property
    def severity_rank(self) -> int:
        return {"warning": 1, "severe": 2, "extreme": 3}.get(self.severity, 0)


# ──────────────────────────────────────────────────────────────────────
# Anomaly Detector
# ──────────────────────────────────────────────────────────────────────


class WeatherAnomalyDetector:
    """Statistical + rule-based anomaly detection for Indian weather data.

    Uses climate normals as baseline and IMD thresholds for event classification.
    """

    # IMD-aligned thresholds
    HEAT_WAVE = {
        "plains":  {"threshold": 40.0, "departure": 4.5, "consecutive_days": 3},
        "coastal": {"threshold": 37.0, "departure": 4.5, "consecutive_days": 3},
        "hills":   {"threshold": 30.0, "departure": 5.0, "consecutive_days": 3},
    }
    COLD_WAVE = {
        "plains":  {"threshold": 4.0, "departure": -4.5, "consecutive_days": 3},
        "coastal": {"threshold": 10.0, "departure": -4.5, "consecutive_days": 3},
        "hills":   {"threshold": -2.0, "departure": -5.0, "consecutive_days": 3},
    }
    EXTREME_RAIN_MM = 204.5       # IMD "extremely heavy rainfall"
    VERY_HEAVY_RAIN_MM = 115.6    # IMD "very heavy rainfall"
    HEAVY_RAIN_MM = 64.5          # IMD "heavy rainfall"
    DROUGHT_SOIL_Z = -1.5
    DROUGHT_PRECIP_PERCENTILE = 20
    DROUGHT_MIN_DAYS = 14
    CYCLONE_WIND_KMH = 90.0

    # ── Z-score computation ──────────────────────────────────────────

    def compute_anomaly_scores(
        self,
        observations: pd.DataFrame,
        normals: pd.DataFrame,
    ) -> pd.DataFrame:
        """Add z-score columns to observations based on monthly climate normals.

        Args:
            observations: DataFrame indexed by date with weather columns.
            normals: DataFrame with columns [month, variable, mean, std].

        Returns:
            observations DataFrame with additional z-score columns.
        """
        df = observations.copy()
        df["_month"] = df.index.month

        # Build lookup: (month, variable) → (mean, std)
        normal_lookup: dict[tuple[int, str], tuple[float, float]] = {}
        for _, row in normals.iterrows():
            normal_lookup[(int(row["month"]), row["variable"])] = (
                float(row["mean"]),
                float(row["std"]),
            )

        score_map = {
            "temperature_max": "temp_max_zscore",
            "temperature_min": "temp_min_zscore",
            "precipitation_sum": "precip_zscore",
            "soil_moisture_mean": "soil_moisture_zscore",
        }

        for var, z_col in score_map.items():
            if var not in df.columns:
                df[z_col] = np.nan
                continue
            z_scores = []
            for idx, row in df.iterrows():
                key = (int(row["_month"]), var)
                if key in normal_lookup:
                    mean, std = normal_lookup[key]
                    if std > 0:
                        z_scores.append((row[var] - mean) / std)
                    else:
                        z_scores.append(0.0)
                else:
                    z_scores.append(np.nan)
            df[z_col] = z_scores

        df.drop(columns=["_month"], inplace=True)
        return df

    # ── Individual anomaly detectors ─────────────────────────────────

    def detect_heat_waves(
        self,
        city: str,
        df: pd.DataFrame,
        normals: pd.DataFrame | None = None,
    ) -> list[DetectedAnomaly]:
        """Detect heat waves using IMD criteria: Tmax above threshold for ≥3 consecutive days."""
        zone = CITY_BY_NAME.get(city, type("", (), {"zone": "plains"})).zone
        rules = self.HEAT_WAVE.get(zone, self.HEAT_WAVE["plains"])
        threshold = rules["threshold"]
        min_days = rules["consecutive_days"]

        if "temperature_max" not in df.columns:
            return []

        return self._detect_consecutive_exceedance(
            city=city,
            series=df["temperature_max"],
            threshold=threshold,
            min_days=min_days,
            anomaly_type="heat_wave",
            above=True,
            z_series=df.get("temp_max_zscore"),
        )

    def detect_cold_waves(
        self,
        city: str,
        df: pd.DataFrame,
        normals: pd.DataFrame | None = None,
    ) -> list[DetectedAnomaly]:
        """Detect cold waves: Tmin below threshold for ≥3 consecutive days."""
        zone = CITY_BY_NAME.get(city, type("", (), {"zone": "plains"})).zone
        rules = self.COLD_WAVE.get(zone, self.COLD_WAVE["plains"])
        threshold = rules["threshold"]
        min_days = rules["consecutive_days"]

        if "temperature_min" not in df.columns:
            return []

        return self._detect_consecutive_exceedance(
            city=city,
            series=df["temperature_min"],
            threshold=threshold,
            min_days=min_days,
            anomaly_type="cold_wave",
            above=False,
            z_series=df.get("temp_min_zscore"),
        )

    def detect_extreme_rainfall(
        self, city: str, df: pd.DataFrame
    ) -> list[DetectedAnomaly]:
        """Detect single-day extreme precipitation events per IMD thresholds."""
        if "precipitation_sum" not in df.columns:
            return []

        anomalies = []
        for idx, row in df.iterrows():
            precip = row["precipitation_sum"]
            if pd.isna(precip):
                continue

            if precip >= self.EXTREME_RAIN_MM:
                severity = "extreme"
            elif precip >= self.VERY_HEAVY_RAIN_MM:
                severity = "severe"
            elif precip >= self.HEAVY_RAIN_MM:
                severity = "warning"
            else:
                continue

            d = idx.date() if hasattr(idx, "date") else idx
            z = row.get("precip_zscore")
            anomalies.append(DetectedAnomaly(
                city=city,
                anomaly_type="extreme_rain",
                severity=severity,
                start_date=d,
                end_date=d,
                peak_value=float(precip),
                z_score=float(z) if z is not None and not pd.isna(z) else None,
            ))
        return anomalies

    def detect_drought_signals(
        self,
        city: str,
        df: pd.DataFrame,
        normals: pd.DataFrame,
    ) -> list[DetectedAnomaly]:
        """Detect drought: soil moisture z < -1.5 AND precip below 20th percentile for ≥14 days."""
        has_soil = "soil_moisture_zscore" in df.columns
        has_precip = "precipitation_sum" in df.columns
        if not has_soil or not has_precip:
            return []

        # Build monthly precip percentile lookup
        precip_p20: dict[int, float] = {}
        for _, row in normals.iterrows():
            if row["variable"] == "precipitation_sum" and row.get("p25") is not None:
                # Use p25 as approximation for p20 (close enough)
                precip_p20[int(row["month"])] = float(row["p25"])

        # Tag each day as drought-flagged
        df = df.copy()
        flags = []
        for idx, row in df.iterrows():
            month = idx.month if hasattr(idx, "month") else 1
            soil_z = row.get("soil_moisture_zscore", 0)
            precip = row.get("precipitation_sum", 0)
            threshold = precip_p20.get(month, 0)

            is_dry = (
                (not pd.isna(soil_z) and soil_z < self.DROUGHT_SOIL_Z)
                and (not pd.isna(precip) and precip < threshold)
            )
            flags.append(is_dry)

        df["_drought_flag"] = flags

        # Find consecutive runs ≥ DROUGHT_MIN_DAYS
        return self._detect_flag_runs(
            city=city,
            dates=df.index,
            flags=df["_drought_flag"].values,
            min_days=self.DROUGHT_MIN_DAYS,
            anomaly_type="drought",
            df=df,
        )

    def detect_cyclone_proxy(
        self, city: str, df: pd.DataFrame
    ) -> list[DetectedAnomaly]:
        """Detect cyclone proxy at coastal stations: wind gusts > 90 km/h + heavy rain."""
        zone = CITY_BY_NAME.get(city, type("", (), {"zone": "plains"})).zone
        if zone != "coastal":
            return []

        has_wind = "wind_gusts_max" in df.columns
        has_precip = "precipitation_sum" in df.columns
        if not has_wind or not has_precip:
            return []

        anomalies = []
        for idx, row in df.iterrows():
            wind = row.get("wind_gusts_max", 0)
            precip = row.get("precipitation_sum", 0)
            if pd.isna(wind) or pd.isna(precip):
                continue

            if wind >= self.CYCLONE_WIND_KMH and precip >= self.HEAVY_RAIN_MM:
                d = idx.date() if hasattr(idx, "date") else idx
                severity = "extreme" if wind >= 120 else ("severe" if wind >= 100 else "warning")
                anomalies.append(DetectedAnomaly(
                    city=city,
                    anomaly_type="cyclone_proxy",
                    severity=severity,
                    start_date=d,
                    end_date=d,
                    peak_value=float(wind),
                ))
        return anomalies

    def detect_unusual_warmth(
        self, city: str, df: pd.DataFrame
    ) -> list[DetectedAnomaly]:
        """Detect days with unusually warm mean temperature (z-score ≥ 1.5)."""
        if "temp_max_zscore" not in df.columns:
            return []

        anomalies = []
        for idx, row in df.iterrows():
            z = row.get("temp_max_zscore")
            if z is None or pd.isna(z):
                continue
            if z >= 2.5:
                severity = "extreme"
            elif z >= 2.0:
                severity = "severe"
            elif z >= 1.5:
                severity = "warning"
            else:
                continue

            d = idx.date() if hasattr(idx, "date") else idx
            anomalies.append(DetectedAnomaly(
                city=city,
                anomaly_type="unusual_warmth",
                severity=severity,
                start_date=d,
                end_date=d,
                peak_value=float(row.get("temperature_max", 0)),
                z_score=float(z),
            ))
        return anomalies

    # ── Master runner ────────────────────────────────────────────────

    def detect_all(
        self,
        city: str,
        df: pd.DataFrame,
        normals: pd.DataFrame,
    ) -> list[DetectedAnomaly]:
        """Run all detectors, deduplicate, and rank by severity."""
        anomalies: list[DetectedAnomaly] = []
        anomalies.extend(self.detect_heat_waves(city, df, normals))
        anomalies.extend(self.detect_cold_waves(city, df, normals))
        anomalies.extend(self.detect_extreme_rainfall(city, df))
        anomalies.extend(self.detect_drought_signals(city, df, normals))
        anomalies.extend(self.detect_cyclone_proxy(city, df))
        anomalies.extend(self.detect_unusual_warmth(city, df))
        return sorted(anomalies, key=lambda a: a.severity_rank, reverse=True)

    # ── Private helpers ──────────────────────────────────────────────

    def _detect_consecutive_exceedance(
        self,
        city: str,
        series: pd.Series,
        threshold: float,
        min_days: int,
        anomaly_type: str,
        above: bool = True,
        z_series: pd.Series | None = None,
    ) -> list[DetectedAnomaly]:
        """Find runs of ≥min_days where values exceed/fall below threshold."""
        if above:
            mask = series >= threshold
        else:
            mask = series <= threshold

        anomalies = []
        run_start = None
        run_values: list[float] = []
        run_zscores: list[float] = []

        for i, (idx, val) in enumerate(series.items()):
            if pd.isna(val):
                # Break run
                if run_start is not None and len(run_values) >= min_days:
                    anomalies.append(self._make_run_anomaly(
                        city, anomaly_type, run_start, idx, run_values, run_zscores, above,
                    ))
                run_start = None
                run_values = []
                run_zscores = []
                continue

            if mask.iloc[i]:
                if run_start is None:
                    run_start = idx
                run_values.append(float(val))
                if z_series is not None:
                    z = z_series.iloc[i]
                    if not pd.isna(z):
                        run_zscores.append(float(z))
            else:
                if run_start is not None and len(run_values) >= min_days:
                    anomalies.append(self._make_run_anomaly(
                        city, anomaly_type, run_start, series.index[i - 1],
                        run_values, run_zscores, above,
                    ))
                run_start = None
                run_values = []
                run_zscores = []

        # Handle run at end of series
        if run_start is not None and len(run_values) >= min_days:
            anomalies.append(self._make_run_anomaly(
                city, anomaly_type, run_start, series.index[-1],
                run_values, run_zscores, above,
            ))

        return anomalies

    def _make_run_anomaly(
        self,
        city: str,
        anomaly_type: str,
        start_idx,
        end_idx,
        values: list[float],
        zscores: list[float],
        above: bool,
    ) -> DetectedAnomaly:
        peak = max(values) if above else min(values)
        avg_z = float(np.mean(zscores)) if zscores else None

        if anomaly_type == "heat_wave":
            severity = "extreme" if peak >= 47 else ("severe" if peak >= 45 else "warning")
        elif anomaly_type == "cold_wave":
            severity = "extreme" if peak <= 0 else ("severe" if peak <= 2 else "warning")
        else:
            severity = "warning"

        start_d = start_idx.date() if hasattr(start_idx, "date") else start_idx
        end_d = end_idx.date() if hasattr(end_idx, "date") else end_idx

        return DetectedAnomaly(
            city=city,
            anomaly_type=anomaly_type,
            severity=severity,
            start_date=start_d,
            end_date=end_d,
            peak_value=peak,
            z_score=avg_z,
        )

    def _detect_flag_runs(
        self,
        city: str,
        dates,
        flags: np.ndarray,
        min_days: int,
        anomaly_type: str,
        df: pd.DataFrame,
    ) -> list[DetectedAnomaly]:
        """Find consecutive runs of True flags ≥ min_days."""
        anomalies = []
        run_start = None
        run_length = 0

        for i, flagged in enumerate(flags):
            if flagged:
                if run_start is None:
                    run_start = i
                run_length += 1
            else:
                if run_start is not None and run_length >= min_days:
                    start_d = dates[run_start]
                    end_d = dates[i - 1]
                    if hasattr(start_d, "date"):
                        start_d = start_d.date()
                    if hasattr(end_d, "date"):
                        end_d = end_d.date()

                    # Average soil moisture z-score over the run
                    z_vals = df.iloc[run_start:i]["soil_moisture_zscore"].dropna()
                    avg_z = float(z_vals.mean()) if len(z_vals) > 0 else None

                    severity = "extreme" if run_length >= 30 else (
                        "severe" if run_length >= 21 else "warning"
                    )
                    anomalies.append(DetectedAnomaly(
                        city=city,
                        anomaly_type=anomaly_type,
                        severity=severity,
                        start_date=start_d,
                        end_date=end_d,
                        peak_value=float(run_length),
                        z_score=avg_z,
                    ))
                run_start = None
                run_length = 0

        # Handle trailing run
        if run_start is not None and run_length >= min_days:
            start_d = dates[run_start]
            end_d = dates[-1]
            if hasattr(start_d, "date"):
                start_d = start_d.date()
            if hasattr(end_d, "date"):
                end_d = end_d.date()
            z_vals = df.iloc[run_start:]["soil_moisture_zscore"].dropna()
            avg_z = float(z_vals.mean()) if len(z_vals) > 0 else None
            severity = "extreme" if run_length >= 30 else (
                "severe" if run_length >= 21 else "warning"
            )
            anomalies.append(DetectedAnomaly(
                city=city,
                anomaly_type=anomaly_type,
                severity=severity,
                start_date=start_d,
                end_date=end_d,
                peak_value=float(run_length),
                z_score=avg_z,
            ))

        return anomalies


# ──────────────────────────────────────────────────────────────────────
# Trend Analyzer
# ──────────────────────────────────────────────────────────────────────


@dataclass
class TrendResult:
    """Result of a linear trend analysis."""
    variable: str
    slope_per_decade: float
    r_squared: float
    p_value: float
    direction: str  # "increasing", "decreasing", "stable"
    start_year: int
    end_year: int


@dataclass
class MonsoonAnalysis:
    """Monsoon season (Jun-Sep) analysis for a city."""
    city: str
    year: int
    total_rainfall_mm: float
    normal_rainfall_mm: float
    deficit_pct: float
    rain_days: int
    heavy_rain_days: int  # days ≥ 64.5mm
    max_single_day_mm: float


class WeatherTrendAnalyzer:
    """Long-term trend analysis for Indian weather data."""

    def compute_annual_trend(
        self,
        observations: pd.DataFrame,
        variable: str,
    ) -> TrendResult | None:
        """Compute linear trend on annual means of a variable.

        Args:
            observations: DataFrame indexed by date with the target variable column.
            variable: Column name to analyze.

        Returns:
            TrendResult with slope expressed as change per decade, or None if insufficient data.
        """
        if variable not in observations.columns:
            return None

        df = observations[[variable]].dropna()
        if len(df) < 365:  # need at least 1 year of data
            return None

        df = df.copy()
        df["year"] = df.index.year
        annual = df.groupby("year")[variable].mean()

        if len(annual) < 3:
            return None

        years = annual.index.values.astype(float)
        values = annual.values.astype(float)

        slope, intercept, r_value, p_value, std_err = sp_stats.linregress(years, values)

        slope_per_decade = slope * 10
        r_squared = r_value ** 2

        if p_value > 0.05:
            direction = "stable"
        elif slope_per_decade > 0:
            direction = "increasing"
        else:
            direction = "decreasing"

        return TrendResult(
            variable=variable,
            slope_per_decade=round(slope_per_decade, 4),
            r_squared=round(r_squared, 4),
            p_value=round(p_value, 6),
            direction=direction,
            start_year=int(years[0]),
            end_year=int(years[-1]),
        )

    def analyze_monsoon(
        self,
        observations: pd.DataFrame,
        normals: pd.DataFrame,
        city: str,
        year: int,
    ) -> MonsoonAnalysis | None:
        """Analyze monsoon season (Jun-Sep) for a given year.

        Args:
            observations: Full year of daily data indexed by date.
            normals: Monthly climate normals DataFrame.
            city: City name.
            year: Year to analyze.

        Returns:
            MonsoonAnalysis or None if insufficient data.
        """
        if "precipitation_sum" not in observations.columns:
            return None

        # Filter to Jun-Sep of the given year
        monsoon = observations[
            (observations.index.month >= 6)
            & (observations.index.month <= 9)
            & (observations.index.year == year)
        ]
        if len(monsoon) < 30:
            return None

        precip = monsoon["precipitation_sum"].dropna()
        total_rain = float(precip.sum())
        rain_days = int((precip > 2.5).sum())  # IMD rain day threshold
        heavy_days = int((precip >= 64.5).sum())
        max_day = float(precip.max())

        # Compute expected normal rainfall for Jun-Sep
        normal_rain = 0.0
        for month in [6, 7, 8, 9]:
            match = normals[
                (normals["month"] == month)
                & (normals["variable"] == "precipitation_sum")
            ]
            if len(match) > 0:
                # mean is the daily mean; multiply by ~30 days
                days_in_month = {6: 30, 7: 31, 8: 31, 9: 30}[month]
                normal_rain += float(match.iloc[0]["mean"]) * days_in_month

        deficit_pct = (
            ((total_rain - normal_rain) / normal_rain * 100)
            if normal_rain > 0
            else 0.0
        )

        return MonsoonAnalysis(
            city=city,
            year=year,
            total_rainfall_mm=round(total_rain, 1),
            normal_rainfall_mm=round(normal_rain, 1),
            deficit_pct=round(deficit_pct, 1),
            rain_days=rain_days,
            heavy_rain_days=heavy_days,
            max_single_day_mm=round(max_day, 1),
        )

    def compute_extreme_frequency(
        self,
        observations: pd.DataFrame,
        variable: str,
        threshold: float,
        above: bool = True,
    ) -> pd.DataFrame:
        """Count days exceeding a threshold per year.

        Returns DataFrame with columns [year, count].
        """
        if variable not in observations.columns:
            return pd.DataFrame(columns=["year", "count"])

        df = observations[[variable]].dropna().copy()
        df["year"] = df.index.year

        if above:
            df["exceeds"] = df[variable] >= threshold
        else:
            df["exceeds"] = df[variable] <= threshold

        counts = df.groupby("year")["exceeds"].sum().reset_index()
        counts.columns = ["year", "count"]
        counts["count"] = counts["count"].astype(int)
        return counts
