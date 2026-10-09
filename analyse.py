
# Part 1: what each policy does across the futures (no machine learning).
# Part 2: which uncertainty matters most for each result (machine learning)..

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_val_score

YEARS = list(range(2023, 2051))
INPUTS = ["demand_2050", "gas_price", "renewable_build", "nuclear_delay"]
INPUT_NAMES = ["Demand 2050", "Gas price", "Renewable build limit", "Nuclear delay"]
RESULTS = {"nuclear_2050": "Nuclear 2050 (GW)", "gas_2050": "Gas 2050 (GW)",
           "co2_total": "CO2 2023-2050 (Mt)", "system_cost": "System cost (bn EUR)"}
COLOURS = {"cap": "#2a78d6", "price": "#eb6834"}
NAMES = {"cap": "Emission cap (original case)", "price": "Carbon price"}

os.makedirs("output", exist_ok=True)      
runs = pd.read_csv("results.csv")
runs["system_cost"] = runs["system_cost"] / 1000          
ok = runs[runs["status"] == "optimal"]


# ---------------------------------------------------------------------------
# Part 1: summary table and pathways figure
# ---------------------------------------------------------------------------
table = []
for policy in ["cap", "price"]:
    data = ok[ok["policy"] == policy]
    row = {"policy": policy,
           "infeasible futures": int((runs["policy"] == policy).sum() - len(data))}
    for column in ["co2_2050", "co2_total", "system_cost", "nuclear_2045", "nuclear_2050", "gas_2050"]:
        p10, median, p90 = np.percentile(data[column], [10, 50, 90])
        row[column + " median"] = round(median, 1)
        row[column + " p10-p90"] = "%.1f - %.1f" % (p10, p90)
    table.append(row)
table = pd.DataFrame(table)
table.to_csv("output/summary.csv", index=False)
print(table.T.to_string())

panels = [("co2", "CO2 emissions (Mt)"), ("nuclear", "Nuclear (GW)"), ("gas", "Gas (GW)"),
          ("wind", "Wind (GW)"), ("solar", "Solar (GW)")]
fig, axes = plt.subplots(1, 5, figsize=(16, 3.5))
for ax, (name, title) in zip(axes, panels):
    for policy in ["cap", "price"]:
        data = ok[ok["policy"] == policy]
        values = data[["%s_%d" % (name, y) for y in YEARS]].values
        p10, median, p90 = np.percentile(values, [10, 50, 90], axis=0)
        ax.fill_between(YEARS, p10, p90, color=COLOURS[policy], alpha=0.15, linewidth=0)
        ax.plot(YEARS, median, color=COLOURS[policy], linewidth=2, label=NAMES[policy])
    ax.set_title(title, loc="left", fontsize=10)
    ax.set_ylim(bottom=0)
    ax.grid(color="#e6e5e1")
axes[0].legend(frameon=False, fontsize=8)
fig.suptitle("Median path (line) and 10-90 % of futures (band)", x=0.01, ha="left")
fig.tight_layout()
fig.savefig("output/fig1_pathways.png", dpi=150)


# ---------------------------------------------------------------------------
# Part 2: which uncertainty matters most (machine learning)
# ---------------------------------------------------------------------------
drivers = []
fig, axes = plt.subplots(2, 4, figsize=(15, 6), sharey=True)
for i, policy in enumerate(["cap", "price"]):
    data = ok[ok["policy"] == policy]
    X = data[INPUTS].values
    for j, result in enumerate(RESULTS):
        ax = axes[i][j]
        ax.set_title(NAMES[policy].split(" (")[0] + " | " + RESULTS[result], loc="left", fontsize=9)
        y = data[result].values
        if np.percentile(y, 90) - np.percentile(y, 10) < 0.01:
            ax.text(0.5, 0.5, "same value in most futures", ha="center", transform=ax.transAxes)
            continue

        forest = RandomForestRegressor(n_estimators=300, min_samples_leaf=3, random_state=0)
        r2_forest = cross_val_score(forest, X, y, cv=5, scoring="r2").mean()
        r2_linear = cross_val_score(LinearRegression(), X, y, cv=5, scoring="r2").mean()

        forest.fit(X, y)
        shuffle = permutation_importance(forest, X, y, n_repeats=20, random_state=0)
        importance = np.maximum(shuffle.importances_mean, 0)
        share = 100 * importance / importance.sum()

        row = {"policy": policy, "result": result,
               "R2 forest": round(r2_forest, 2), "R2 linear": round(r2_linear, 2)}
        for k in range(len(INPUTS)):
            row[INPUT_NAMES[k] + " %"] = round(share[k])
        drivers.append(row)

        ax.barh(INPUT_NAMES, share, color=COLOURS[policy])
        ax.set_xlim(0, 100)
        ax.grid(axis="x", color="#e6e5e1")
        ax.set_title(NAMES[policy].split(" (")[0] + " | " + RESULTS[result] +
                     "\nR2 forest %.2f, R2 linear %.2f" % (r2_forest, r2_linear), loc="left", fontsize=9)
for ax in axes[1]:
    ax.set_xlabel("importance (%)")
axes[0][0].invert_yaxis()
fig.suptitle("Which uncertainty matters most? (random forest + permutation importance)", x=0.01, ha="left")
fig.tight_layout()
fig.savefig("output/fig2_drivers.png", dpi=150)

drivers = pd.DataFrame(drivers)
drivers.to_csv("output/drivers.csv", index=False)
print()
print(drivers.to_string(index=False))


# ---------------------------------------------------------------------------
# One example in the raw data: a threshold that a straight line cannot describe
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(6, 4))
data = ok[ok["policy"] == "cap"]
ax.scatter(data["gas_price"], data["co2_total"], s=15, color=COLOURS["cap"])
ax.set_xlabel("Gas price (1.0 = price in the original data)")
ax.set_ylabel("CO2 2023-2050 (Mt)")
ax.set_title("Emission cap: cumulative CO2 vs gas price (one dot = one future)", loc="left", fontsize=10)
ax.grid(color="#e6e5e1")
fig.tight_layout()
fig.savefig("output/fig3_gas_threshold.png", dpi=150)
print("\nsaved two tables and three figures in output/")
