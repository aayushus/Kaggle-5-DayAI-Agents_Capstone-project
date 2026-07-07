from __future__ import annotations

def compute(competitor_prices: list[float], n_global_customers: float = 5_000_000.0, n_target_customers: float = 50_000.0, capture_rate: float = 0.01) -> dict[str, float]:
    price = sum(competitor_prices) / len(competitor_prices) if competitor_prices else 49.0
    annual = float(price) * 12.0
    tam = float(n_global_customers) * annual
    sam = float(n_target_customers) * annual
    som = sam * float(capture_rate)
    return {
        "monthly_price": float(price),
        "annual_price": annual,
        "tam": tam,
        "sam": sam,
        "som": som,
        "formulae": {
            "annual_price": "monthly_price * 12",
            "bottom_up_tam": "n_global_customers * annual_price",
            "bottom_up_sam": "n_target_customers * annual_price",
            "bottom_up_som": "bottom_up_sam * capture_rate",
        },
    }


if __name__ == "__main__":
    print(compute([49.0, 99.0]))
