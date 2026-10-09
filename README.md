# Climate policy under uncertainty in an OSeMOSYS model of Poland

**Question.** Poland's power system can be pushed towards zero emissions with an emission cap or with a carbon
price. How do the two policies behave when the future is uncertain, and which uncertainty have the most impact?

**Method.**
1. Take an existing OSeMOSYS model of the Polish power system (built in MUIO, 2023-2050, electricity only).
   The model equations are not changed.
2. Draw 150 possible futures (demand, gas price, how fast wind and solar can be built, nuclear delay).
3. Solve every future under both policies: 300 runs of the real model.
4. Compare the policies across the futures (no machine learning).
5. Use a random forest to find which uncertainty drives each result (machine learning).

## The two policies

| Policy | What it is |
|---|---|
| Emission cap (`cap`) | Based on Poland's NECP: emissions at most 78.7 Mt/yr in 2030-39, 25.8 Mt/yr in 2040-49, 0 in 2050 |
| Carbon price (`price`) | No emission cap. Emitting costs 60 EUR/t in 2026, rising in a straight line to 200 EUR/t in 2050 |

## The four uncertainties

| Uncertainty | Range | What changes in the data |
|---|---|---|
| Electricity demand in 2050 | 0.9 - 1.3 x original | `SpecifiedAnnualDemand`, changing gradually from 2026 |
| Gas price | 0.7 - 1.8 x original | `VariableCost` of gas supply, from 2026 |
| Wind and solar build limit | 0.6 - 1.4 x original | `TotalAnnualMaxCapacityInvestment` of wind and solar, from 2026 |
| Nuclear delay | 0 - 8 years | the nuclear rows of `TotalAnnualMaxCapacityInvestment` and `TotalAnnualMinCapacityInvestment` (Plants that are planned to be constructed) move later |

The ranges are illustrative, not forecasts. Years before 2026 are not changed.

## Files

```
model/model_muio_v5.3.txt   OSeMOSYS model file shipped with MUIO v5.3 
model/data_poland.txt       the data file exported from MUIO
model/data_processed.txt    the same data plus the extra sets MUIO adds before solving 
run_experiment.py           changes the data, solves the model, saves results.csv
analyse.py                  Trains ML random forest, analyses results, makes the tables and figures in output/
results.csv                 the 300 runs (one row per run)
output/                     summary.csv, drivers.csv and three figures
```

## How to run

1. Install Python 3.10+ and the packages: `pip install -r requirements.txt`
2. Find `glpsol.exe` and `cbc.exe` inside the MUIO folder and write their full paths at the top of
   `run_experiment.py` (`GLPSOL = r"C:\...\glpsol.exe"`, `CBC = r"C:\...\cbc.exe"`).
   On Mac/Linux you can install them instead (`brew install glpk cbc`) and leave `"glpsol"` and `"cbc"`.
3. "Calibration check": `python run_experiment.py check` must print 133000.64811 twice (the MUIO objective of the original case).
4. `python run_experiment.py` solves the 300 runs and writes `results.csv`.
5. `python analyse.py` writes the tables and figures to `output/`.

## Results

| | Emission cap | Carbon price |
|---|---|---|
| CO2 in 2050 (Mt), median (10-90 % of futures) | 0 (0 - 0) | 16 (11 - 24) |
| CO2 2023-2050 (Mt) | 1,490 (1,442 - 1,534) | 834 (712 - 956) |
| System cost (bn EUR) | 142 (126 - 165) | 160 (145 - 179) |
| Nuclear 2045 / 2050 (GW) | 3.8 / 11.7 | 3.8 / 3.8 |


* The cap always reaches zero in 2050, but emissions
  stay high until the 2030s. The price cuts emissions to about 19 Mt by 2030 and cumulative emissions by about 45 %, but never reaches zero.
* New nuclear appears only with the cap, to reach exactly zero in 2050. It is built mostly after 2045
  part of this is an end-of-horizon effect of the model.
* Demand is the main driver of nuclear, gas and cost under both policies.
* The random forest is needed where the model has thresholds. Under the cap, cumulative CO2 depends on the gas
  price when it is 20% cheaper because cheap gas replaces coal earlier. A linear regression explains 15 % of it,
  the random forest 73 %. Under the price policy, new nuclear is only built when gas is expensive (linear 48 %,
  forest 90 %). Where the effect is close to a straight line (cost), both do equally well.


System cost = discounted cost 2023-2050 without carbon payments.


## Why machine learning, and where it could go

In this project the model is small: one run takes about 3 seconds, so every future can simply be
solved. Machine learning is used to read its results:
after 150 futures, it is not visible by eye which uncertainty causes what, because all of them
change at the same time. A random forest learns the link between the uncertain inputs and each
result, and permutation importance shows which input matters most.

Before trusting it, the random forest is tested using 2 on futures it has not seen. It predicts the solver's results well (R2 0.73 to 0.98). This becomes useful for larger models. A multi-region model with hourly detail, can take hours per run, so thousands of scenarios cannot
be solved. A model like this random forest, trained on a few hundred real runs, could then predict the results of new scenarios in a shorter time. Two limits apply: it can only be
trusted inside the ranges it was trained on, and it must always be checked against real runs.

## Limitations

* Small model: one region, 8 time slices per year, perfect foresight.
* Illustrative ranges: with other ranges the ranking of drivers can change.
* Results after about 2045 are affected by the end of the model horizon.

## Ethics and attribution

- The OSeMOSYS model of Poland (`model/data_poland.txt`) was built by [Emilia Ramos Hidalgo, Sonali Sonali, Rose Capistrant, Mia Reichow]. It is used here with the agreement of my co-authors. 
- The code was written with the help of an AI assistant (Claude).
- The OSeMOSYS model file is the one distributed with MUIO v5.3 (open source, Apache 2.0 licence).
