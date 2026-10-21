# Data cleaning note (22 Oct 2026)
The Yahoo daily archive has 119 non-reverting one-day jumps > 40% (unadjusted splits/bonuses, mostly 2005-2010, e.g. ABB +443% on 2007-06-28).
From now on backtests use a cleaned copy where each affected stock (95 of 499) starts the day after its last such jump.
Effect: momentum rotation 34.2% -> 31.7% CAGR (after tax 28.0% -> 26.1%); 3 PM breakout 26.0% -> 24.0% (from 2007, Rs 20L);
LST + market filter + 20-EMA trail 27.3% -> 24.1%; MST + filter + 20-EMA trail 14.8% -> 14.4%.
