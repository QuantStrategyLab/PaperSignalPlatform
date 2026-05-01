# MAG7 Specialist + Unified Momentum Overlay

Window: `2022-01-03` to requested `2026-05-01`.
Trading cost: 15.0 bps per unit turnover.
Overlay score is identical for every underlying: QQQ > SMA150, stock > SMA150, 60d momentum > 0, 120d momentum > 0, then rank by 20d/60d/120d momentum, risk-adjusted 60d momentum, and 60d relative strength vs QQQ.
The overlay only decides which underlyings may receive allocation; tool choice and per-route volatility sizing still use the current specialist routes.

## Performance

| overlay | mode | cagr | max_drawdown | total_return | sharpe | avg_cash | avg_top_weight | avg_tactical_active_count | rebalance_days | first_return_date | latest_return_date | observations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | static_score | 42.30% | -31.22% | 358.22% | 1.14 | 42.08% | 29.01% | 2.62 | 348 | 2022-01-04 | 2026-04-29 | 1083 |
| none | dynamic_score | 44.39% | -32.11% | 388.00% | 1.17 | 42.23% | 31.01% | 2.62 | 677 | 2022-01-04 | 2026-04-29 | 1083 |
| none | dynamic_sqrt_score | 42.65% | -30.99% | 363.12% | 1.18 | 42.14% | 27.32% | 2.62 | 664 | 2022-01-04 | 2026-04-29 | 1083 |
| top2 | static_score | 37.14% | -35.18% | 290.68% | 1.10 | 58.33% | 31.91% | 1.20 | 301 | 2022-01-04 | 2026-04-29 | 1083 |
| top2 | dynamic_score | 38.24% | -34.98% | 304.42% | 1.12 | 58.41% | 32.56% | 1.20 | 564 | 2022-01-04 | 2026-04-29 | 1083 |
| top2 | dynamic_sqrt_score | 37.27% | -35.19% | 292.30% | 1.12 | 58.01% | 30.07% | 1.20 | 543 | 2022-01-04 | 2026-04-29 | 1083 |
| top3 | static_score | 52.05% | -32.21% | 509.90% | 1.40 | 55.34% | 29.33% | 1.64 | 298 | 2022-01-04 | 2026-04-29 | 1083 |
| top3 | dynamic_score | 53.46% | -32.10% | 534.70% | 1.42 | 55.49% | 30.36% | 1.64 | 620 | 2022-01-04 | 2026-04-29 | 1083 |
| top3 | dynamic_sqrt_score | 52.41% | -30.56% | 516.12% | 1.44 | 55.34% | 26.92% | 1.64 | 605 | 2022-01-04 | 2026-04-29 | 1083 |
| top4 | static_score | 48.53% | -34.80% | 451.27% | 1.33 | 53.47% | 27.84% | 1.97 | 330 | 2022-01-04 | 2026-04-29 | 1083 |
| top4 | dynamic_score | 51.19% | -33.60% | 495.12% | 1.38 | 53.62% | 28.97% | 1.97 | 640 | 2022-01-04 | 2026-04-29 | 1083 |
| top4 | dynamic_sqrt_score | 49.57% | -32.02% | 468.18% | 1.40 | 53.52% | 25.35% | 1.97 | 627 | 2022-01-04 | 2026-04-29 | 1083 |
| top5 | static_score | 47.15% | -33.50% | 429.48% | 1.31 | 52.24% | 26.99% | 2.17 | 343 | 2022-01-04 | 2026-04-29 | 1083 |
| top5 | dynamic_score | 48.92% | -33.96% | 457.61% | 1.33 | 52.40% | 28.35% | 2.17 | 642 | 2022-01-04 | 2026-04-29 | 1083 |
| top5 | dynamic_sqrt_score | 47.38% | -33.14% | 433.14% | 1.36 | 52.31% | 24.79% | 2.17 | 629 | 2022-01-04 | 2026-04-29 | 1083 |

## Calendar Years

| overlay | mode | year | return | max_drawdown | sharpe |
| --- | --- | --- | --- | --- | --- |
| none | static_score | 2022 | -29.37% | -26.31% | -2.00 |
| none | static_score | 2023 | 95.30% | -18.09% | 2.03 |
| none | static_score | 2024 | 175.26% | -31.22% | 2.25 |
| none | static_score | 2025 | 20.92% | -28.65% | 0.71 |
| none | static_score | 2026 | -0.20% | -20.55% | 0.13 |
| none | dynamic_score | 2022 | -29.35% | -26.17% | -1.99 |
| none | dynamic_score | 2023 | 89.59% | -19.40% | 1.91 |
| none | dynamic_score | 2024 | 185.81% | -32.11% | 2.27 |
| none | dynamic_score | 2025 | 21.81% | -27.61% | 0.73 |
| none | dynamic_score | 2026 | 4.65% | -18.32% | 0.63 |
| none | dynamic_sqrt_score | 2022 | -28.64% | -25.46% | -1.97 |
| none | dynamic_sqrt_score | 2023 | 86.60% | -18.72% | 1.92 |
| none | dynamic_sqrt_score | 2024 | 175.52% | -30.99% | 2.31 |
| none | dynamic_sqrt_score | 2025 | 21.92% | -27.24% | 0.75 |
| none | dynamic_sqrt_score | 2026 | 3.54% | -18.85% | 0.52 |
| top2 | static_score | 2022 | -0.59% | -2.17% | -0.25 |
| top2 | static_score | 2023 | 70.04% | -16.83% | 1.68 |
| top2 | static_score | 2024 | 80.48% | -35.18% | 1.43 |
| top2 | static_score | 2025 | 21.07% | -23.90% | 0.77 |
| top2 | static_score | 2026 | 5.77% | -16.11% | 0.80 |
| top2 | dynamic_score | 2022 | -0.59% | -2.17% | -0.25 |
| top2 | dynamic_score | 2023 | 66.50% | -16.68% | 1.63 |
| top2 | dynamic_score | 2024 | 87.37% | -34.98% | 1.49 |
| top2 | dynamic_score | 2025 | 23.29% | -24.24% | 0.82 |
| top2 | dynamic_score | 2026 | 5.77% | -16.11% | 0.80 |
| top2 | dynamic_sqrt_score | 2022 | -0.59% | -2.17% | -0.25 |
| top2 | dynamic_sqrt_score | 2023 | 58.54% | -17.95% | 1.53 |
| top2 | dynamic_sqrt_score | 2024 | 87.18% | -35.19% | 1.52 |
| top2 | dynamic_sqrt_score | 2025 | 25.89% | -23.72% | 0.90 |
| top2 | dynamic_sqrt_score | 2026 | 5.63% | -16.11% | 0.79 |
| top3 | static_score | 2022 | -0.59% | -2.17% | -0.25 |
| top3 | static_score | 2023 | 83.93% | -17.18% | 1.96 |
| top3 | static_score | 2024 | 164.84% | -29.68% | 2.13 |
| top3 | static_score | 2025 | 20.54% | -25.47% | 0.77 |
| top3 | static_score | 2026 | 4.48% | -15.52% | 0.65 |
| top3 | dynamic_score | 2022 | -0.59% | -2.17% | -0.25 |
| top3 | dynamic_score | 2023 | 81.47% | -16.80% | 1.93 |
| top3 | dynamic_score | 2024 | 166.10% | -30.28% | 2.12 |
| top3 | dynamic_score | 2025 | 25.75% | -24.14% | 0.90 |
| top3 | dynamic_score | 2026 | 5.14% | -15.52% | 0.73 |
| top3 | dynamic_sqrt_score | 2022 | -0.59% | -2.17% | -0.25 |
| top3 | dynamic_sqrt_score | 2023 | 76.02% | -17.73% | 1.90 |
| top3 | dynamic_sqrt_score | 2024 | 165.09% | -29.13% | 2.19 |
| top3 | dynamic_sqrt_score | 2025 | 26.33% | -23.18% | 0.94 |
| top3 | dynamic_sqrt_score | 2026 | 5.14% | -15.52% | 0.74 |
| top4 | static_score | 2022 | -0.59% | -2.17% | -0.25 |
| top4 | static_score | 2023 | 81.91% | -15.35% | 1.92 |
| top4 | static_score | 2024 | 175.25% | -28.09% | 2.24 |
| top4 | static_score | 2025 | 10.88% | -30.02% | 0.49 |
| top4 | static_score | 2026 | -0.12% | -16.02% | 0.12 |
| top4 | dynamic_score | 2022 | -0.59% | -2.17% | -0.25 |
| top4 | dynamic_score | 2023 | 78.09% | -15.22% | 1.86 |
| top4 | dynamic_score | 2024 | 176.74% | -29.22% | 2.22 |
| top4 | dynamic_score | 2025 | 18.86% | -27.16% | 0.71 |
| top4 | dynamic_score | 2026 | 2.19% | -16.02% | 0.39 |
| top4 | dynamic_sqrt_score | 2022 | -0.59% | -2.17% | -0.25 |
| top4 | dynamic_sqrt_score | 2023 | 74.00% | -15.99% | 1.87 |
| top4 | dynamic_sqrt_score | 2024 | 169.29% | -27.89% | 2.27 |
| top4 | dynamic_sqrt_score | 2025 | 19.33% | -25.56% | 0.74 |
| top4 | dynamic_sqrt_score | 2026 | 2.22% | -16.02% | 0.39 |
| top5 | static_score | 2022 | -0.59% | -2.17% | -0.25 |
| top5 | static_score | 2023 | 89.65% | -15.98% | 2.07 |
| top5 | static_score | 2024 | 145.43% | -29.91% | 2.03 |
| top5 | static_score | 2025 | 12.76% | -30.92% | 0.53 |
| top5 | static_score | 2026 | 1.48% | -16.02% | 0.30 |
| top5 | dynamic_score | 2022 | -0.59% | -2.17% | -0.25 |
| top5 | dynamic_score | 2023 | 82.02% | -15.65% | 1.94 |
| top5 | dynamic_score | 2024 | 156.03% | -31.05% | 2.08 |
| top5 | dynamic_score | 2025 | 16.80% | -29.72% | 0.64 |
| top5 | dynamic_score | 2026 | 3.05% | -16.02% | 0.49 |
| top5 | dynamic_sqrt_score | 2022 | -0.59% | -2.17% | -0.25 |
| top5 | dynamic_sqrt_score | 2023 | 78.45% | -15.34% | 1.98 |
| top5 | dynamic_sqrt_score | 2024 | 150.06% | -29.81% | 2.13 |
| top5 | dynamic_sqrt_score | 2025 | 16.61% | -28.17% | 0.65 |
| top5 | dynamic_sqrt_score | 2026 | 3.06% | -16.02% | 0.49 |

## Tactical Leaders

| overlay | mode | leader | days | share |
| --- | --- | --- | --- | --- |
| none | static_score | NVDA | 557 | 72.72% |
| none | static_score | GOOGL | 104 | 13.58% |
| none | static_score | TSLA | 47 | 6.14% |
| none | static_score | META | 39 | 5.09% |
| none | static_score | MSFT | 9 | 1.17% |
| none | static_score | AAPL | 7 | 0.91% |
| none | static_score | AMZN | 3 | 0.39% |
| none | dynamic_score | NVDA | 550 | 71.80% |
| none | dynamic_score | GOOGL | 80 | 10.44% |
| none | dynamic_score | TSLA | 61 | 7.96% |
| none | dynamic_score | META | 52 | 6.79% |
| none | dynamic_score | AAPL | 11 | 1.44% |
| none | dynamic_score | MSFT | 9 | 1.17% |
| none | dynamic_score | AMZN | 3 | 0.39% |
| none | dynamic_sqrt_score | NVDA | 496 | 64.75% |
| none | dynamic_sqrt_score | GOOGL | 106 | 13.84% |
| none | dynamic_sqrt_score | TSLA | 87 | 11.36% |
| none | dynamic_sqrt_score | META | 54 | 7.05% |
| none | dynamic_sqrt_score | AAPL | 11 | 1.44% |
| none | dynamic_sqrt_score | MSFT | 9 | 1.17% |
| none | dynamic_sqrt_score | AMZN | 3 | 0.39% |
| top2 | static_score | NVDA | 415 | 56.85% |
| top2 | static_score | GOOGL | 138 | 18.90% |
| top2 | static_score | TSLA | 79 | 10.82% |
| top2 | static_score | META | 62 | 8.49% |
| top2 | static_score | MSFT | 22 | 3.01% |
| top2 | static_score | AAPL | 11 | 1.51% |
| top2 | static_score | AMZN | 3 | 0.41% |
| top2 | dynamic_score | NVDA | 413 | 56.58% |
| top2 | dynamic_score | GOOGL | 117 | 16.03% |
| top2 | dynamic_score | TSLA | 102 | 13.97% |
| top2 | dynamic_score | META | 62 | 8.49% |
| top2 | dynamic_score | MSFT | 23 | 3.15% |
| top2 | dynamic_score | AAPL | 11 | 1.51% |
| top2 | dynamic_score | AMZN | 2 | 0.27% |
| top2 | dynamic_sqrt_score | NVDA | 412 | 56.44% |
| top2 | dynamic_sqrt_score | GOOGL | 118 | 16.16% |
| top2 | dynamic_sqrt_score | TSLA | 101 | 13.84% |
| top2 | dynamic_sqrt_score | META | 63 | 8.63% |
| top2 | dynamic_sqrt_score | MSFT | 23 | 3.15% |
| top2 | dynamic_sqrt_score | AAPL | 11 | 1.51% |
| top2 | dynamic_sqrt_score | AMZN | 2 | 0.27% |
| top3 | static_score | NVDA | 477 | 64.90% |
| top3 | static_score | GOOGL | 128 | 17.41% |
| top3 | static_score | TSLA | 51 | 6.94% |
| top3 | static_score | META | 46 | 6.26% |
| top3 | static_score | MSFT | 19 | 2.59% |
| top3 | static_score | AAPL | 12 | 1.63% |
| top3 | static_score | AMZN | 2 | 0.27% |
| top3 | dynamic_score | NVDA | 471 | 64.08% |
| top3 | dynamic_score | GOOGL | 100 | 13.61% |
| top3 | dynamic_score | TSLA | 82 | 11.16% |
| top3 | dynamic_score | META | 48 | 6.53% |
| top3 | dynamic_score | MSFT | 19 | 2.59% |
| top3 | dynamic_score | AAPL | 13 | 1.77% |
| top3 | dynamic_score | AMZN | 2 | 0.27% |
| top3 | dynamic_sqrt_score | NVDA | 457 | 62.18% |
| top3 | dynamic_sqrt_score | GOOGL | 108 | 14.69% |
| top3 | dynamic_sqrt_score | TSLA | 86 | 11.70% |
| top3 | dynamic_sqrt_score | META | 50 | 6.80% |
| top3 | dynamic_sqrt_score | MSFT | 19 | 2.59% |
| top3 | dynamic_sqrt_score | AAPL | 13 | 1.77% |
| top3 | dynamic_sqrt_score | AMZN | 2 | 0.27% |
| top4 | static_score | NVDA | 508 | 69.02% |
| top4 | static_score | GOOGL | 121 | 16.44% |
| top4 | static_score | TSLA | 39 | 5.30% |
| top4 | static_score | META | 37 | 5.03% |
| top4 | static_score | MSFT | 19 | 2.58% |
| top4 | static_score | AAPL | 10 | 1.36% |
| top4 | static_score | AMZN | 2 | 0.27% |
| top4 | dynamic_score | NVDA | 502 | 68.21% |
| top4 | dynamic_score | GOOGL | 87 | 11.82% |
| top4 | dynamic_score | TSLA | 72 | 9.78% |
| top4 | dynamic_score | META | 41 | 5.57% |
| top4 | dynamic_score | MSFT | 19 | 2.58% |
| top4 | dynamic_score | AAPL | 13 | 1.77% |
| top4 | dynamic_score | AMZN | 2 | 0.27% |
| top4 | dynamic_sqrt_score | NVDA | 471 | 63.99% |
| top4 | dynamic_sqrt_score | GOOGL | 107 | 14.54% |
| top4 | dynamic_sqrt_score | TSLA | 81 | 11.01% |
| top4 | dynamic_sqrt_score | META | 43 | 5.84% |
| top4 | dynamic_sqrt_score | MSFT | 19 | 2.58% |
| top4 | dynamic_sqrt_score | AAPL | 13 | 1.77% |
| top4 | dynamic_sqrt_score | AMZN | 2 | 0.27% |
| top5 | static_score | NVDA | 528 | 71.74% |
| top5 | static_score | GOOGL | 112 | 15.22% |
| top5 | static_score | TSLA | 37 | 5.03% |
| top5 | static_score | META | 28 | 3.80% |
| top5 | static_score | MSFT | 19 | 2.58% |
| top5 | static_score | AAPL | 10 | 1.36% |
| top5 | static_score | AMZN | 2 | 0.27% |
| top5 | dynamic_score | NVDA | 522 | 70.92% |
| top5 | dynamic_score | GOOGL | 80 | 10.87% |
| top5 | dynamic_score | TSLA | 65 | 8.83% |
| top5 | dynamic_score | META | 37 | 5.03% |
| top5 | dynamic_score | MSFT | 19 | 2.58% |
| top5 | dynamic_score | AAPL | 11 | 1.49% |
| top5 | dynamic_score | AMZN | 2 | 0.27% |
| top5 | dynamic_sqrt_score | NVDA | 478 | 64.95% |
| top5 | dynamic_sqrt_score | GOOGL | 106 | 14.40% |
| top5 | dynamic_sqrt_score | TSLA | 81 | 11.01% |
| top5 | dynamic_sqrt_score | META | 39 | 5.30% |
| top5 | dynamic_sqrt_score | MSFT | 19 | 2.58% |
| top5 | dynamic_sqrt_score | AAPL | 11 | 1.49% |
| top5 | dynamic_sqrt_score | AMZN | 2 | 0.27% |

## Average Weights

| symbol | none | top2 | top3 | top4 | top5 |
| --- | --- | --- | --- | --- | --- |
| NVDL | 15.40% | 16.34% | 16.19% | 15.99% | 15.81% |
| FBL | 7.97% | 7.44% | 7.75% | 7.36% | 7.16% |
| NVDA | 7.28% | 0.44% | 0.81% | 1.32% | 1.63% |
| GGLL | 7.14% | 6.75% | 6.72% | 7.00% | 7.18% |
| TSLL | 6.14% | 5.03% | 5.24% | 5.24% | 5.34% |
| AMZN | 3.82% | 1.57% | 2.52% | 3.28% | 3.96% |
| AAPU | 3.37% | 1.68% | 2.17% | 2.50% | 2.60% |
| TSLA | 2.71% | 0.08% | 0.08% | 0.14% | 0.14% |
| META | 2.11% | 0.54% | 1.02% | 1.39% | 1.62% |
| MSFU | 1.17% | 1.55% | 1.52% | 1.61% | 1.62% |
| AMZU | 0.75% | 0.56% | 0.64% | 0.66% | 0.64% |
