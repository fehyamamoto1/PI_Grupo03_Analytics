from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

HORIZON = 7
MIN_DAYS = 35
_LAGS = (1, 7, 14)


def daily_item_series(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame(columns=["item_id", "item_name", "date", "quantity"])

    grid = (
        sales.groupby(["item_id", "item_name", "date"], as_index=False)["quantity"].sum()
    )
    days = pd.date_range(grid["date"].min(), grid["date"].max(), freq="D")
    keys = grid[["item_id", "item_name"]].drop_duplicates()
    full = keys.merge(pd.DataFrame({"date": days}), how="cross")
    out = full.merge(grid, on=["item_id", "item_name", "date"], how="left")
    out["quantity"] = out["quantity"].fillna(0.0)
    return out.sort_values(["item_id", "date"]).reset_index(drop=True)


def _features(series: pd.DataFrame) -> pd.DataFrame:
    df = series.copy()
    df["weekday"] = df["date"].dt.day_of_week
    df["is_weekend"] = (df["weekday"] >= 4).astype(int)
    df["trend"] = np.arange(len(df))
    for lag in _LAGS:
        df[f"lag{lag}"] = df["quantity"].shift(lag)
    df["roll7"] = df["quantity"].shift(1).rolling(7, min_periods=3).mean()
    df["roll28"] = df["quantity"].shift(1).rolling(28, min_periods=7).mean()
    return df


_FEATURE_COLS = ["weekday", "is_weekend", "trend", "roll7", "roll28"] + [
    f"lag{lag}" for lag in _LAGS
]


def _baseline_predict(history: pd.DataFrame, dates) -> np.ndarray:
    preds = []
    for when in pd.to_datetime(pd.Series(list(dates))):
        same = history.loc[history["date"].dt.day_of_week == when.weekday(), "quantity"]
        preds.append(float(same.tail(4).median()) if len(same) else 0.0)
    return np.array(preds)


def evaluate_item(series: pd.DataFrame, splits: int = 3) -> dict | None:
    frame = _features(series).dropna(subset=_FEATURE_COLS)
    if len(frame) < MIN_DAYS:
        return None

    n_splits = max(2, min(splits, (len(frame) - 1) // HORIZON))
    tscv = TimeSeriesSplit(n_splits=n_splits, test_size=HORIZON)
    m_true, m_pred, b_pred = [], [], []

    for train_idx, test_idx in tscv.split(frame):
        train, test = frame.iloc[train_idx], frame.iloc[test_idx]
        model = RandomForestRegressor(
            n_estimators=220, min_samples_leaf=2, random_state=42, n_jobs=-1
        )
        model.fit(train[_FEATURE_COLS], train["quantity"])
        m_pred.extend(model.predict(test[_FEATURE_COLS]))
        b_pred.extend(_baseline_predict(train, test["date"]))
        m_true.extend(test["quantity"].to_numpy())

    m_true = np.array(m_true)
    model_mae = float(mean_absolute_error(m_true, m_pred))
    base_mae = float(mean_absolute_error(m_true, b_pred))
    return {
        "n_days": len(frame),
        "folds": n_splits,
        "model_mae": round(model_mae, 2),
        "model_rmse": round(float(np.sqrt(mean_squared_error(m_true, m_pred))), 2),
        "baseline_mae": round(base_mae, 2),
        "baseline_rmse": round(float(np.sqrt(mean_squared_error(m_true, b_pred))), 2),
        "gain_pct": round(100.0 * (base_mae - model_mae) / base_mae, 1) if base_mae else 0.0,
        "winner": "modelo" if model_mae < base_mae else "baseline",
    }


def forecast_item(series: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    hist = series[["date", "quantity"]].copy()
    future = pd.date_range(
        hist["date"].max() + pd.Timedelta(days=1), periods=horizon, freq="D"
    )

    frame = _features(series).dropna(subset=_FEATURE_COLS)
    if len(frame) < MIN_DAYS:
        return pd.DataFrame({
            "date": future,
            "quantity": _baseline_predict(hist, future),
            "source": "baseline",
        })

    model = RandomForestRegressor(
        n_estimators=220, min_samples_leaf=2, random_state=42, n_jobs=-1
    )
    model.fit(frame[_FEATURE_COLS], frame["quantity"])

    working = hist.copy()
    trend_start = len(series)
    preds = []
    for step, when in enumerate(future):
        q = working["quantity"]
        row = {
            "weekday": when.weekday(),
            "is_weekend": int(when.weekday() >= 4),
            "trend": trend_start + step,
            "roll7": float(q.tail(7).mean()),
            "roll28": float(q.tail(28).mean()),
        }
        for lag in _LAGS:
            row[f"lag{lag}"] = float(q.iloc[-lag]) if len(q) >= lag else float(q.mean())
        value = float(model.predict(pd.DataFrame([row])[_FEATURE_COLS])[0])
        value = max(value, 0.0)
        preds.append(value)
        working = pd.concat(
            [working, pd.DataFrame([{"date": when, "quantity": value}])],
            ignore_index=True,
        )

    return pd.DataFrame({"date": future, "quantity": preds, "source": "modelo"})


def forecast_all(sales: pd.DataFrame, horizon: int = HORIZON) -> tuple:
    series_all = daily_item_series(sales)
    empty = pd.DataFrame()
    if series_all.empty:
        return empty, empty, empty

    daily_rows, totals, scores = [], [], []
    for (item_id, item_name), group in series_all.groupby(["item_id", "item_name"]):
        group = group.sort_values("date").reset_index(drop=True)

        forecast = forecast_item(group, horizon)
        forecast["item_id"] = item_id
        forecast["item_name"] = item_name
        daily_rows.append(forecast)

        totals.append({
            "item_id": item_id,
            "item_name": item_name,
            "quantity": float(forecast["quantity"].sum()),
            "horizon_days": horizon,
        })

        score = evaluate_item(group)
        if score:
            score.update({"item_name": item_name, "item_id": item_id})
            scores.append(score)

    daily = pd.concat(daily_rows, ignore_index=True) if daily_rows else empty
    return daily, pd.DataFrame(totals), pd.DataFrame(scores)


def forecast_band(series: pd.DataFrame, forecast: pd.DataFrame) -> pd.DataFrame:
    out = forecast.copy()
    resid = series["quantity"].tail(56)
    spread = float(resid.std()) if len(resid) > 3 else 0.0
    out["low"] = (out["quantity"] - spread).clip(lower=0.0)
    out["high"] = out["quantity"] + spread
    return out
