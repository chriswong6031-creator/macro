# OPEX/Vanna/Charm Robustness Addendum (Fable adjudication)

Generated: 2026-07-06T13:12:49.025180+00:00

## 1. Control strength (the confound itself)
- Era1_2017_2019 trail_rv20 -> realized_vol_5d: IC=0.50182, t=53.9914.
- Era1_2017_2019 trail_rv20 -> abs_move_5d: IC=0.27833, t=33.6165.
- Era2_2020_2022 trail_rv20 -> realized_vol_5d: IC=0.58008, t=48.5695.
- Era2_2020_2022 trail_rv20 -> abs_move_5d: IC=0.30926, t=33.139.
- Era3_2023_2026 trail_rv20 -> realized_vol_5d: IC=0.5943, t=74.1163.
- Era3_2023_2026 trail_rv20 -> abs_move_5d: IC=0.35618, t=42.725.
- Era1_2017_2019 log_oi_notional -> realized_vol_5d: IC=-0.16456, t=-11.0428.
- Era1_2017_2019 log_oi_notional -> abs_move_5d: IC=-0.08405, t=-7.9527.
- Era2_2020_2022 log_oi_notional -> realized_vol_5d: IC=-0.16337, t=-10.3021.
- Era2_2020_2022 log_oi_notional -> abs_move_5d: IC=-0.08901, t=-7.2704.
- Era3_2023_2026 log_oi_notional -> realized_vol_5d: IC=-0.11218, t=-9.0859.
- Era3_2023_2026 log_oi_notional -> abs_move_5d: IC=-0.0594, t=-5.9725.

## 2. Raw vs vol/size-residualized partial ICs (full universe)

| feature | target | era | raw IC | partial IC | retained | t(part) | adj_p | survives |
|---|---|---|---|---|---|---|---|---|
| charm_intensity | abs_move_5d | Era1_2017_2019 | -0.0663 | 0.03588 | -0.5412 | 6.4244 | 0.0 | YES |
| charm_intensity | abs_move_5d | Era2_2020_2022 | -0.07166 | 0.03282 | -0.458 | 5.8693 | 0.0 | YES |
| charm_intensity | abs_move_5d | Era3_2023_2026 | -0.029 | 0.05633 | -1.9426 | 11.5195 | 0.0 | YES |
| charm_intensity | realized_vol_5d | Era1_2017_2019 | -0.13456 | 0.05785 | -0.4299 | 8.1573 | 0.0 | YES |
| charm_intensity | realized_vol_5d | Era2_2020_2022 | -0.13461 | 0.05531 | -0.4109 | 7.9873 | 0.0 | YES |
| charm_intensity | realized_vol_5d | Era3_2023_2026 | -0.06261 | 0.09938 | -1.5872 | 15.0701 | 0.0 | YES |
| front_week_charm_concentration | abs_move_5d | Era1_2017_2019 | 0.09518 | 0.0412 | 0.4329 | 6.1994 | 0.0 | YES |
| front_week_charm_concentration | abs_move_5d | Era2_2020_2022 | 0.13278 | 0.04323 | 0.3256 | 6.5189 | 0.0 | YES |
| front_week_charm_concentration | abs_move_5d | Era3_2023_2026 | 0.20842 | 0.06891 | 0.3306 | 11.2599 | 0.0 | YES |
| front_week_charm_concentration | realized_vol_5d | Era1_2017_2019 | 0.14639 | 0.05947 | 0.4063 | 6.5352 | 0.0 | YES |
| front_week_charm_concentration | realized_vol_5d | Era2_2020_2022 | 0.24072 | 0.07727 | 0.321 | 9.1218 | 0.0 | YES |
| front_week_charm_concentration | realized_vol_5d | Era3_2023_2026 | 0.33991 | 0.12994 | 0.3823 | 17.807 | 0.0 | YES |
| front_week_gamma_concentration | abs_move_5d | Era1_2017_2019 | 0.07696 | 0.03966 | 0.5153 | 6.3038 | 0.0 | YES |
| front_week_gamma_concentration | abs_move_5d | Era2_2020_2022 | 0.11479 | 0.04179 | 0.3641 | 5.7219 | 0.0 | YES |
| front_week_gamma_concentration | abs_move_5d | Era3_2023_2026 | 0.18897 | 0.05823 | 0.3082 | 10.1561 | 0.0 | YES |
| front_week_gamma_concentration | realized_vol_5d | Era1_2017_2019 | 0.11002 | 0.05172 | 0.4701 | 5.9238 | 0.0 | YES |
| front_week_gamma_concentration | realized_vol_5d | Era2_2020_2022 | 0.19646 | 0.06356 | 0.3235 | 7.7639 | 0.0 | YES |
| front_week_gamma_concentration | realized_vol_5d | Era3_2023_2026 | 0.30877 | 0.11333 | 0.367 | 15.443 | 0.0 | YES |
| gamma_intensity | abs_move_5d | Era1_2017_2019 | -0.10808 | -0.09669 | 0.8946 | -15.2099 | 0.0 | YES |
| gamma_intensity | abs_move_5d | Era2_2020_2022 | -0.10982 | -0.07616 | 0.6935 | -12.5187 | 0.0 | YES |
| gamma_intensity | abs_move_5d | Era3_2023_2026 | -0.10073 | -0.11985 | 1.1899 | -18.4428 | 0.0 | YES |
| gamma_intensity | realized_vol_5d | Era1_2017_2019 | -0.20432 | -0.16199 | 0.7928 | -21.2758 | 0.0 | YES |
| gamma_intensity | realized_vol_5d | Era2_2020_2022 | -0.20251 | -0.1478 | 0.7298 | -18.5797 | 0.0 | YES |
| gamma_intensity | realized_vol_5d | Era3_2023_2026 | -0.17935 | -0.21537 | 1.2008 | -28.1399 | 0.0 | YES |
| signed_charm_pressure | abs_move_5d | Era1_2017_2019 | 0.0322 | -0.00084 | -0.026 | -0.1467 | 0.883418 | no |
| signed_charm_pressure | abs_move_5d | Era2_2020_2022 | 0.04701 | -0.00243 | -0.0517 | -0.486 | 0.675379 | no |
| signed_charm_pressure | abs_move_5d | Era3_2023_2026 | 0.07961 | -0.00755 | -0.0949 | -1.4229 | 0.171442 | no |
| signed_charm_pressure | realized_vol_5d | Era1_2017_2019 | 0.05139 | -0.00346 | -0.0673 | -0.4477 | 0.67793 | no |
| signed_charm_pressure | realized_vol_5d | Era2_2020_2022 | 0.10638 | 0.01817 | 0.1708 | 2.6214 | 0.01014 | YES |
| signed_charm_pressure | realized_vol_5d | Era3_2023_2026 | 0.14354 | 0.00283 | 0.0197 | 0.4376 | 0.67793 | no |
| vanna_hedge_pressure_5d_ivmove | abs_move_5d | Era1_2017_2019 | -0.01946 | -0.03654 | 1.8779 | -6.0291 | 0.0 | YES |
| vanna_hedge_pressure_5d_ivmove | abs_move_5d | Era2_2020_2022 | -0.02296 | -0.03717 | 1.6194 | -7.4976 | 0.0 | YES |
| vanna_hedge_pressure_5d_ivmove | abs_move_5d | Era3_2023_2026 | -0.01807 | -0.04159 | 2.3016 | -8.4987 | 0.0 | YES |
| vanna_hedge_pressure_5d_ivmove | realized_vol_5d | Era1_2017_2019 | -0.03107 | -0.05316 | 1.7112 | -6.8959 | 0.0 | YES |
| vanna_hedge_pressure_5d_ivmove | realized_vol_5d | Era2_2020_2022 | -0.02458 | -0.04924 | 2.0033 | -8.6056 | 0.0 | YES |
| vanna_hedge_pressure_5d_ivmove | realized_vol_5d | Era3_2023_2026 | -0.03218 | -0.06886 | 2.1402 | -9.762 | 0.0 | YES |
| vanna_intensity | abs_move_5d | Era1_2017_2019 | -0.11661 | -0.13146 | 1.1273 | -17.5145 | 0.0 | YES |
| vanna_intensity | abs_move_5d | Era2_2020_2022 | -0.12146 | -0.10524 | 0.8665 | -15.4166 | 0.0 | YES |
| vanna_intensity | abs_move_5d | Era3_2023_2026 | -0.12568 | -0.15442 | 1.2286 | -19.4646 | 0.0 | YES |
| vanna_intensity | realized_vol_5d | Era1_2017_2019 | -0.21748 | -0.21359 | 0.9821 | -23.1593 | 0.0 | YES |
| vanna_intensity | realized_vol_5d | Era2_2020_2022 | -0.22252 | -0.19494 | 0.8761 | -20.2989 | 0.0 | YES |
| vanna_intensity | realized_vol_5d | Era3_2023_2026 | -0.21959 | -0.27906 | 1.2708 | -34.3637 | 0.0 | YES |

## 3. Real ETF/index/sector slice (the slice F-15/16/17/20 cited without artifact)
- ETF panel: 49254 rows, 21 roots, 2017-01-04 to 2026-07-02.

### ETF cross-section survivors (BH-FDR 10% within slice)
- Era2_2020_2022 signed_charm_pressure -> realized_vol_5d: IC=0.13675, t=7.4336, adj_p=0.0.
- Era1_2017_2019 charm_intensity -> abs_move_5d: IC=-0.10963, t=-9.2758, adj_p=0.0.
- Era1_2017_2019 charm_intensity -> realized_vol_5d: IC=-0.19667, t=-14.0341, adj_p=0.0.
- Era3_2023_2026 charm_intensity -> realized_vol_5d: IC=-0.07213, t=-5.5144, adj_p=0.0.
- Era3_2023_2026 front_week_charm_concentration -> abs_move_5d: IC=0.07861, t=5.8227, adj_p=0.0.
- Era3_2023_2026 front_week_charm_concentration -> realized_vol_5d: IC=0.1341, t=9.4315, adj_p=0.0.
- Era2_2020_2022 signed_vanna_pressure -> abs_move_5d: IC=-0.08974, t=-5.7225, adj_p=0.0.
- Era2_2020_2022 signed_vanna_pressure -> realized_vol_5d: IC=-0.20551, t=-8.1928, adj_p=0.0.
- Era1_2017_2019 vanna_intensity -> abs_move_5d: IC=-0.15601, t=-13.1118, adj_p=0.0.
- Era1_2017_2019 vanna_intensity -> realized_vol_5d: IC=-0.29142, t=-19.7607, adj_p=0.0.
- Era2_2020_2022 vanna_intensity -> abs_move_5d: IC=-0.11926, t=-10.0348, adj_p=0.0.
- Era2_2020_2022 vanna_intensity -> realized_vol_5d: IC=-0.20305, t=-16.1672, adj_p=0.0.
- Era3_2023_2026 vanna_intensity -> abs_move_5d: IC=-0.14375, t=-13.1056, adj_p=0.0.
- Era3_2023_2026 vanna_intensity -> realized_vol_5d: IC=-0.24675, t=-18.474, adj_p=0.0.
- Era1_2017_2019 signed_gamma_pressure -> abs_move_5d: IC=-0.13135, t=-10.0222, adj_p=0.0.
- Era1_2017_2019 signed_gamma_pressure -> realized_vol_5d: IC=-0.22571, t=-11.7908, adj_p=0.0.
- Era2_2020_2022 signed_gamma_pressure -> abs_move_5d: IC=-0.08142, t=-5.5232, adj_p=0.0.
- Era2_2020_2022 signed_gamma_pressure -> realized_vol_5d: IC=-0.14308, t=-6.8078, adj_p=0.0.
- Era1_2017_2019 gamma_intensity -> abs_move_5d: IC=-0.14813, t=-12.2696, adj_p=0.0.
- Era1_2017_2019 gamma_intensity -> realized_vol_5d: IC=-0.28013, t=-19.3781, adj_p=0.0.
- Era2_2020_2022 gamma_intensity -> abs_move_5d: IC=-0.11162, t=-9.7145, adj_p=0.0.
- Era2_2020_2022 gamma_intensity -> realized_vol_5d: IC=-0.1839, t=-13.6948, adj_p=0.0.
- Era3_2023_2026 gamma_intensity -> abs_move_5d: IC=-0.13115, t=-12.3948, adj_p=0.0.
- Era3_2023_2026 gamma_intensity -> realized_vol_5d: IC=-0.22491, t=-17.2691, adj_p=0.0.
- Era1_2017_2019 front_week_gamma_concentration -> realized_vol_5d: IC=-0.10471, t=-5.6069, adj_p=0.0.
- Era3_2023_2026 front_week_gamma_concentration -> abs_move_5d: IC=0.07605, t=5.722, adj_p=0.0.
- Era3_2023_2026 front_week_gamma_concentration -> realized_vol_5d: IC=0.12858, t=9.1272, adj_p=0.0.
- Era1_2017_2019 put_call_oi_ratio -> realized_vol_5d: IC=0.12794, t=5.8982, adj_p=0.0.
- Era1_2017_2019 put_call_oi_ratio -> abs_move_5d: IC=0.07848, t=4.9668, adj_p=6e-06.
- Era3_2023_2026 signed_gamma_pressure -> realized_vol_5d: IC=-0.10616, t=-4.764, adj_p=1.1e-05.
- Era3_2023_2026 signed_charm_pressure -> rel_ret_10d: IC=0.08275, t=4.4642, adj_p=4.8e-05.
- Era3_2023_2026 signed_charm_pressure -> realized_vol_5d: IC=0.08003, t=4.2929, adj_p=0.000103.
- Era1_2017_2019 front_week_charm_concentration -> realized_vol_5d: IC=-0.07598, t=-4.1951, adj_p=0.000155.
- Era3_2023_2026 put_call_oi_ratio -> abs_move_5d: IC=-0.04915, t=-3.9459, adj_p=0.000417.
- Era3_2023_2026 signed_charm_pressure -> rel_ret_1d: IC=0.03536, t=3.8233, adj_p=0.000665.
- Era1_2017_2019 front_week_gamma_concentration -> abs_move_5d: IC=-0.0498, t=-3.787, adj_p=0.000756.
- Era3_2023_2026 signed_charm_pressure -> rel_ret_5d: IC=0.05721, t=3.7055, adj_p=0.000999.
- Era3_2023_2026 charm_intensity -> abs_move_5d: IC=-0.04098, t=-3.6208, adj_p=0.00135.
- Era3_2023_2026 signed_vanna_pressure -> realized_vol_5d: IC=-0.07884, t=-3.3112, adj_p=0.004091.
- Era3_2023_2026 put_call_oi_ratio -> realized_vol_5d: IC=-0.06253, t=-3.235, adj_p=0.00521.
- Era1_2017_2019 signed_charm_pressure -> abs_move_5d: IC=0.0397, t=3.1831, adj_p=0.006105.
- Era3_2023_2026 signed_gamma_pressure -> abs_move_5d: IC=-0.04812, t=-3.1598, adj_p=0.006419.
- Era2_2020_2022 signed_charm_pressure -> abs_move_5d: IC=0.04025, t=3.0847, adj_p=0.008104.
- Era3_2023_2026 vanna_hedge_pressure_1d_ivmove -> realized_vol_5d: IC=-0.02172, t=-3.0366, adj_p=0.00924.
- Era3_2023_2026 vanna_hedge_pressure_5d_ivmove -> realized_vol_5d: IC=-0.03575, t=-3.0223, adj_p=0.009467.
- Era1_2017_2019 front_week_charm_concentration -> abs_move_5d: IC=-0.03777, t=-2.923, adj_p=0.012809.
- Era3_2023_2026 front_week_charm_concentration -> rel_ret_1d: IC=0.0262, t=2.8797, adj_p=0.01432.
- Era3_2023_2026 charm_intensity -> rel_ret_10d: IC=0.0479, t=2.7925, adj_p=0.01838.
- Era3_2023_2026 charm_intensity -> rel_ret_5d: IC=0.03287, t=2.7477, adj_p=0.020628.
- Era1_2017_2019 signed_charm_pressure -> realized_vol_5d: IC=0.03795, t=2.5292, adj_p=0.038402.
- Era3_2023_2026 signed_charm_pressure -> abs_move_5d: IC=0.03901, t=2.5134, adj_p=0.039267.
- Era2_2020_2022 vanna_hedge_pressure_5d_ivmove -> abs_move_5d: IC=-0.02779, t=-2.4537, adj_p=0.045578.
- Era3_2023_2026 signed_vanna_pressure -> rel_ret_10d: IC=-0.05821, t=-2.4328, adj_p=0.047016.
- Era3_2023_2026 signed_vanna_pressure -> rel_ret_1d: IC=-0.02372, t=-2.4279, adj_p=0.047016.
- Era3_2023_2026 signed_vanna_pressure -> abs_move_5d: IC=-0.04268, t=-2.3036, adj_p=0.064443.
- Era3_2023_2026 charm_intensity -> rel_ret_1d: IC=0.01505, t=2.2894, adj_p=0.065682.
- Era3_2023_2026 signed_vanna_pressure -> rel_ret_5d: IC=-0.04099, t=-2.2563, adj_p=0.070348.
- Era2_2020_2022 put_call_oi_ratio -> abs_move_5d: IC=0.02727, t=2.1696, adj_p=0.086332.

### ETF state-spread survivors (BH-FDR 10% within slice)
- Era1_2017_2019 opex_long_gamma_high_charm_pin -> abs_move_5d: spread -0.4125pp, t=-8.8828, adj_p=0.0.
- Era1_2017_2019 opex_long_gamma_high_charm_pin -> realized_vol_5d: spread -3.5666pp, t=-10.9146, adj_p=0.0.
- Era3_2023_2026 opex_long_gamma_high_charm_pin -> realized_vol_5d: spread -2.9679pp, t=-5.339, adj_p=0.0.
- Era1_2017_2019 quad_opex_high_charm -> realized_vol_5d: spread -1.7053pp, t=-5.974, adj_p=0.0.
- Era1_2017_2019 vanna_relief_buy_pressure -> realized_vol_5d: spread -1.1935pp, t=-5.8537, adj_p=0.0.
- Era2_2020_2022 vanna_relief_buy_pressure -> abs_move_5d: spread -0.3495pp, t=-5.8221, adj_p=0.0.
- Era2_2020_2022 vanna_relief_buy_pressure -> realized_vol_5d: spread -3.2632pp, t=-7.8886, adj_p=0.0.
- Era3_2023_2026 vanna_relief_buy_pressure -> abs_move_5d: spread -0.4309pp, t=-5.7816, adj_p=0.0.
- Era3_2023_2026 vanna_relief_buy_pressure -> realized_vol_5d: spread -3.8786pp, t=-5.3853, adj_p=0.0.
- Era1_2017_2019 vanna_drag_sell_pressure -> realized_vol_5d: spread -1.3885pp, t=-8.9696, adj_p=0.0.
- Era2_2020_2022 vanna_drag_sell_pressure -> realized_vol_5d: spread -2.6247pp, t=-6.0841, adj_p=0.0.
- Era3_2023_2026 vanna_drag_sell_pressure -> abs_move_5d: spread -0.3218pp, t=-6.35, adj_p=0.0.
- Era3_2023_2026 vanna_drag_sell_pressure -> realized_vol_5d: spread -2.3636pp, t=-5.2522, adj_p=0.0.
- Era1_2017_2019 placebo_long_gamma_high_charm_non_opex -> abs_move_5d: spread -0.3682pp, t=-8.8142, adj_p=0.0.
- Era1_2017_2019 placebo_long_gamma_high_charm_non_opex -> realized_vol_5d: spread -3.5655pp, t=-14.8996, adj_p=0.0.
- Era2_2020_2022 placebo_long_gamma_high_charm_non_opex -> realized_vol_5d: spread -3.1625pp, t=-5.9181, adj_p=0.0.
- Era3_2023_2026 opex_long_gamma_high_charm_pin -> abs_move_5d: spread -0.3751pp, t=-4.9464, adj_p=8e-06.
- Era1_2017_2019 vanna_drag_sell_pressure -> abs_move_5d: spread -0.1446pp, t=-4.6747, adj_p=1.6e-05.
- Era2_2020_2022 placebo_long_gamma_high_charm_non_opex -> abs_move_5d: spread -0.3853pp, t=-4.478, adj_p=3.8e-05.
- Era3_2023_2026 placebo_long_gamma_high_charm_non_opex -> abs_move_5d: spread -0.6129pp, t=-3.9594, adj_p=0.00031.
- Era2_2020_2022 opex_long_gamma_high_charm_pin -> abs_move_5d: spread -0.2982pp, t=-4.0418, adj_p=0.000315.
- Era2_2020_2022 opex_long_gamma_high_charm_pin -> realized_vol_5d: spread -2.8001pp, t=-3.9295, adj_p=0.000458.
- Era3_2023_2026 placebo_long_gamma_high_charm_non_opex -> realized_vol_5d: spread -5.5953pp, t=-3.7173, adj_p=0.000698.
- Era2_2020_2022 vanna_drag_sell_pressure -> abs_move_5d: spread -0.184pp, t=-3.6012, adj_p=0.001023.
- Era1_2017_2019 quad_opex_high_charm -> abs_move_5d: spread -0.2619pp, t=-3.0144, adj_p=0.011203.
- Era1_2017_2019 vanna_relief_buy_pressure -> abs_move_5d: spread -0.0989pp, t=-2.6914, adj_p=0.020221.
- Era1_2017_2019 opex_short_gamma_high_charm_airpocket -> realized_vol_5d: spread 1.6045pp, t=2.5938, adj_p=0.028104.
- Era3_2023_2026 vanna_drag_sell_pressure -> rel_ret_2d: spread -0.0781pp, t=-2.2374, adj_p=0.065669.
- Era3_2023_2026 vanna_drag_sell_pressure -> rel_ret_5d: spread -0.1374pp, t=-2.2147, adj_p=0.067191.
- Era2_2020_2022 quad_opex_high_charm -> realized_vol_5d: spread -2.1061pp, t=-2.2024, adj_p=0.075746.
- Era2_2020_2022 vanna_relief_buy_pressure -> rel_ret_2d: spread -0.078pp, t=-2.0317, adj_p=0.098914.

### ETF pin/air-pocket cells (all, survivors or not — the F-15/16 claims)
- Era1_2017_2019 opex_long_gamma_high_charm_pin -> abs_move_5d: spread -0.4125pp, t=-8.8828, p=0.0, adj_p=0.0, n_dates=147, n_cond=714.
- Era1_2017_2019 opex_long_gamma_high_charm_pin -> realized_vol_5d: spread -3.5666pp, t=-10.9146, p=0.0, adj_p=0.0, n_dates=147, n_cond=714.
- Era3_2023_2026 opex_long_gamma_high_charm_pin -> realized_vol_5d: spread -2.9679pp, t=-5.339, p=0.0, adj_p=0.0, n_dates=170, n_cond=818.
- Era3_2023_2026 opex_long_gamma_high_charm_pin -> abs_move_5d: spread -0.3751pp, t=-4.9464, p=2e-06, adj_p=8e-06, n_dates=170, n_cond=818.
- Era2_2020_2022 opex_long_gamma_high_charm_pin -> abs_move_5d: spread -0.2982pp, t=-4.0418, p=9.2e-05, adj_p=0.000315, n_dates=127, n_cond=545.
- Era2_2020_2022 opex_long_gamma_high_charm_pin -> realized_vol_5d: spread -2.8001pp, t=-3.9295, p=0.00014, adj_p=0.000458, n_dates=127, n_cond=545.
- Era1_2017_2019 opex_short_gamma_high_charm_airpocket -> realized_vol_5d: spread 1.6045pp, t=2.5938, p=0.010539, adj_p=0.028104, n_dates=136, n_cond=504.
- Era3_2023_2026 opex_short_gamma_high_charm_airpocket -> abs_move_5d: spread -0.2033pp, t=-1.9216, p=0.056801, adj_p=0.123929, n_dates=134, n_cond=585.
- Era1_2017_2019 opex_short_gamma_high_charm_airpocket -> abs_move_5d: spread 0.138pp, t=1.4378, p=0.152794, adj_p=0.282081, n_dates=136, n_cond=504.
- Era2_2020_2022 opex_short_gamma_high_charm_airpocket -> abs_move_5d: spread -0.1198pp, t=-0.6759, p=0.500157, adj_p=0.734324, n_dates=147, n_cond=658.
- Era2_2020_2022 opex_short_gamma_high_charm_airpocket -> realized_vol_5d: spread 0.772pp, t=0.6325, p=0.528039, adj_p=0.738598, n_dates=147, n_cond=658.
- Era3_2023_2026 opex_short_gamma_high_charm_airpocket -> realized_vol_5d: spread -0.1187pp, t=-0.1229, p=0.902378, adj_p=0.96972, n_dates=134, n_cond=585.

