# China reversal — does a subsector-state gate help?

3-month within-sector reversal, deepest quintile (LO=0.8). Gross + net-of-cost (10.0bps/side, round-trip on the replaced sleeve). Leak-free sector state (engine.china_sector_pathway._position, own-history percentile). FDR=Benjamini-Hochberg across all era×variant cells (α=0.10).

```
era    variant        n sel  gross%   net%  grSh  netSh  maxdd   hit     IC  t_hac  p_hac  FDR✓
-----------------------------------------------------------------------------------------------
full   FLAT         393 111   0.631  0.532  0.67   0.57  -27.1 0.547 0.0472   5.56    0.0   yes
full   WASHED-OUT   226  66   0.469  0.348  0.38   0.28  -31.5 0.558 0.0547   4.41    0.0   yes
full   LEADING      243  53   0.495   0.37   0.4    0.3  -40.0 0.506  0.035   2.69 0.0071   yes
2015+  FLAT         137 229   0.368  0.272  0.55   0.41  -17.5 0.533 0.0422   3.36 0.0008   yes
2015+  WASHED-OUT    94  90   0.223  0.102  0.18   0.08  -31.5 0.532 0.0533   3.11 0.0018   yes
2015+  LEADING      110  82   0.409  0.284  0.31   0.22  -40.0 0.491 0.0272   1.56 0.1185     —
2021+  FLAT          65 279   0.158  0.063  0.24   0.09  -17.5 0.523 0.0405   2.21 0.0271   yes
2021+  WASHED-OUT    47  92  -0.206 -0.322 -0.15  -0.23  -29.1 0.511 0.0656   2.55 0.0109   yes
2021+  LEADING       60 116  -0.399 -0.518 -0.32  -0.42  -40.0   0.4  0.013   0.56 0.5721     —
```

WASHED-OUT = sector state ≤35 (beaten down); LEADING = ≥65 (stretched/euphoric, the original 'gate to leading subsectors' idea); FLAT = no subsector gate.
