from langchain_core.tools import tool
from typing import Optional


@tool
def calculate_risk_score(
    pe_ratio: Optional[float],
    sentiment_score: float,
    price: Optional[float],
    week52_high: Optional[float],
    week52_low: Optional[float],
) -> dict:
    """
    Calculate a composite risk score (0-100) for a stock position.
    Higher score = higher risk. Uses P/E ratio, sentiment, and
    price position within 52-week range.

    Use this when you need to quantify overall investment risk or
    compare risk levels across stocks.

    Args:
        pe_ratio:        Trailing P/E ratio (None if unavailable)
        sentiment_score: Sentiment from -1.0 to +1.0
        price:           Current stock price
        week52_high:     52-week high price
        week52_low:      52-week low price
    """
    components = {}
    total_weight = 0.0
    weighted_score = 0.0

    # Component 1: P/E valuation risk (weight 40%)
    if pe_ratio is not None:
        if pe_ratio < 0:
            pe_score = 90      # negative P/E = company losing money
        elif pe_ratio <= 15:
            pe_score = 10      # value territory
        elif pe_ratio <= 25:
            pe_score = 30
        elif pe_ratio <= 50:
            pe_score = 60
        else:
            pe_score = 85      # highly overvalued territory
        components["pe_risk"] = {"score": pe_score, "pe_ratio": pe_ratio}
        weighted_score += pe_score * 0.40
        total_weight    += 0.40

    # Component 2: Sentiment risk (weight 35%)
    # Flip: bearish sentiment → high risk
    sentiment_risk = round((1.0 - sentiment_score) / 2.0 * 100, 1)
    components["sentiment_risk"] = {"score": sentiment_risk, "sentiment": sentiment_score}
    weighted_score += sentiment_risk * 0.35
    total_weight    += 0.35

    # Component 3: Price position in 52W range (weight 25%)
    if price and week52_high and week52_low and (week52_high - week52_low) > 0:
        position = (price - week52_low) / (week52_high - week52_low)
        # Near 52W high → higher risk of reversion
        position_risk = round(position * 100, 1)
        components["position_risk"] = {
            "score":       position_risk,
            "pct_of_range": round(position * 100, 1),
        }
        weighted_score += position_risk * 0.25
        total_weight    += 0.25

    composite = round(weighted_score / total_weight, 1) if total_weight > 0 else 50.0

    return {
        "composite_risk_score": composite,
        "risk_level": (
            "LOW"    if composite < 30 else
            "MEDIUM" if composite < 60 else
            "HIGH"
        ),
        "components":  components,
        "risk_flag":   composite >= 60,
        "explanation": f"Composite risk score of {composite}/100 based on valuation, sentiment, and price momentum.",
    }


@tool
def calculate_fair_value_range(
    pe_ratio: Optional[float],
    price: Optional[float],
    sector: str = "Technology",
) -> dict:
    """
    Estimate a simple fair-value price range using sector-average P/E benchmarks.
    Use when the user asks if a stock is overvalued or undervalued.

    Args:
        pe_ratio: Current trailing P/E ratio
        price:    Current stock price
        sector:   Company sector for benchmark P/E selection
    """
    # Sector median P/E benchmarks (approximate)
    sector_pe = {
        "Technology":          28,
        "Healthcare":          22,
        "Consumer Cyclical":   20,
        "Consumer Defensive":  20,
        "Financial Services":  13,
        "Energy":              12,
        "Utilities":           18,
        "Real Estate":         35,
        "Industrials":         20,
        "Materials":           17,
        "Communication Services": 22,
    }

    benchmark_pe = sector_pe.get(sector, 20)

    if not pe_ratio or not price or pe_ratio <= 0:
        return {
            "error": "Insufficient data for fair value calculation",
            "benchmark_pe": benchmark_pe,
            "sector": sector,
        }

    # Implied EPS from current price and P/E
    eps = price / pe_ratio

    fair_value_low  = round(eps * (benchmark_pe * 0.85), 2)
    fair_value_mid  = round(eps * benchmark_pe,           2)
    fair_value_high = round(eps * (benchmark_pe * 1.15),  2)
    upside_pct      = round((fair_value_mid - price) / price * 100, 1)

    return {
        "current_price":    price,
        "current_pe":       pe_ratio,
        "benchmark_pe":     benchmark_pe,
        "sector":           sector,
        "fair_value_low":   fair_value_low,
        "fair_value_mid":   fair_value_mid,
        "fair_value_high":  fair_value_high,
        "implied_upside_pct": upside_pct,
        "verdict": (
            "OVERVALUED"   if upside_pct < -15 else
            "SLIGHTLY_OVERVALUED" if upside_pct < 0 else
            "FAIRLY_VALUED" if upside_pct < 15 else
            "UNDERVALUED"
        ),
    }


@tool
def generate_position_sizing(
    portfolio_value: float,
    risk_score: float,
    conviction: str = "medium",
) -> dict:
    """
    Suggest position sizing for a stock given portfolio size and risk.
    Use when users ask how much to invest or what allocation to use.

    Args:
        portfolio_value: Total investable portfolio in INR
        risk_score:      Composite risk score 0-100 from calculate_risk_score
        conviction:      Investment conviction: "low", "medium", or "high"
    """
    conviction_multiplier = {"low": 0.5, "medium": 1.0, "high": 1.5}.get(conviction, 1.0)

    # Base allocation % decreases as risk increases
    if risk_score < 30:
        base_pct = 8.0
    elif risk_score < 60:
        base_pct = 5.0
    else:
        base_pct = 2.5

    adjusted_pct    = min(base_pct * conviction_multiplier, 15.0)  # cap at 15%
    inr_amount   = round(portfolio_value * adjusted_pct / 100, 2)
    stop_loss_pct   = 8 if risk_score < 30 else 6 if risk_score < 60 else 4
    stop_loss_price_offset = stop_loss_pct  # % below entry

    return {
        "recommended_allocation_pct": round(adjusted_pct, 1),
        "recommended_inr_amount":  inr_amount,
        "stop_loss_pct_below_entry":  stop_loss_price_offset,
        "max_loss_if_stopped":        round(inr_amount * stop_loss_pct / 100, 2),
        "rationale": (
            f"{round(adjusted_pct,1)}% allocation ({conviction} conviction, "
            f"risk score {risk_score}/100). "
            f"Set stop-loss {stop_loss_pct}% below entry price."
        ),
    }