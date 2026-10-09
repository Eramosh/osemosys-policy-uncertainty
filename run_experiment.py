# Solve the Poland OSeMOSYS model for many uncertain futures, under two climate policies.

import csv
import os
import subprocess
import sys

import numpy as np

# ----------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------
GLPSOL = r"C:\Users\emili\AppData\Local\muio\app-5.3.0\resources\app\app\WebAPP\SOLVERs\GLPK\glpsol.exe"     # glpsol Insert path to glpsol.exe
CBC = r"C:\Users\emili\AppData\Local\muio\app-5.3.0\resources\app\app\WebAPP\SOLVERs\COIN-OR\cbc.exe"           #cbc Insert path to cbc.exe
MODEL_FILE = "model/model_muio_v5.3.txt"
DATA_FILE = "model/data_processed.txt"
RESULTS_FILE = "results.csv"
MUIO_OBJECTIVE = 133000.64811218

YEARS = list(range(2023, 2051))
N_FUTURES = 150
SEED = 1

# Uncertainties, 1.0 = value in the original data.
# changes are applied from 2026
DEMAND_2050 = (0.9, 1.3)       # electricity demand in 2050 (changes gradually from 2026)
GAS_PRICE = (0.7, 1.8)         # gas price
RENEWABLE_BUILD = (0.6, 1.4)   # max new solar and wind capacity per year
NUCLEAR_DELAY = (0, 8)         # years the nuclear programme is delayed

# Carbon price policy: 60 EUR/t in 2026, rising linearly to 200 EUR/t in 2050
PRICE_2026 = 60.0
PRICE_2050 = 200.0

GROUPS = {"coal": ["PWRCHP", "PWRCOAH", "PWRCOALI"], "gas": ["PWRGAS"], "nuclear": ["PWRNUC"],
          "wind": ["PWRWNDS", "PWRWNDO"], "solar": ["PWRSOLU", "PWRSOLS"]}


# ----------------------------------------------------------------------------
# Small helpers to read and change rows of the data file
# ----------------------------------------------------------------------------
def find_row(lines, param, label):
    """Line number of the row that starts with `label` inside 'param <param> ...'."""
    inside = False
    for i in range(len(lines)):
        words = lines[i].split()
        if len(words) >= 2 and words[0] == "param":
            inside = (words[1] == param)
        elif inside and len(words) > 0 and words[0] == label:
            return i
    return None


def read_row(lines, i):
    return [float(x) for x in lines[i].split()[1:]]


def write_row(lines, i, values):
    label = lines[i].split()[0]
    lines[i] = label + " " + " ".join("%.10g" % v for v in values)


def find_gas_row(lines):
    """The gas price row is inside VariableCost, in the block that starts with [RE1,MINGAS,*,*]."""
    for i in range(len(lines)):
        if lines[i].startswith("[RE1,MINGAS,*,*]"):
            return i + 2      # block header, then the line with the years, then the row
    return None


# ----------------------------------------------------------------------------
# Changes to the data
# ----------------------------------------------------------------------------
def change_demand(lines, demand_2050):
    i = find_row(lines, "SpecifiedAnnualDemand", "ELC002")
    values = read_row(lines, i)
    for k in range(len(YEARS)):
        if YEARS[k] >= 2026:
            factor = 1 + (demand_2050 - 1) * (YEARS[k] - 2025) / 25    # reaches demand_2050 in 2050
            values[k] = values[k] * factor
    write_row(lines, i, values)


def change_gas_price(lines, gas_price):
    i = find_gas_row(lines)
    values = read_row(lines, i)
    for k in range(len(YEARS)):
        if YEARS[k] >= 2026:
            values[k] = values[k] * gas_price
    write_row(lines, i, values)


def change_renewable_build(lines, factor):
    for tech in ["PWRSOLU", "PWRSOLS", "PWRWNDS", "PWRWNDO"]:
        i = find_row(lines, "TotalAnnualMaxCapacityInvestment", tech)
        values = read_row(lines, i)
        j = find_row(lines, "TotalAnnualMinCapacityInvestment", tech)
        forced = read_row(lines, j) if j is not None else [0.0] * len(YEARS)
        for k in range(len(YEARS)):
            if YEARS[k] >= 2026:
                values[k] = max(values[k] * factor, forced[k])     # never below a forced investment
        write_row(lines, i, values)


def delay_nuclear(lines, years):
    """Move the nuclear rows of maximum and forced new capacity `years` years later."""
    for param in ["TotalAnnualMaxCapacityInvestment", "TotalAnnualMinCapacityInvestment"]:
        i = find_row(lines, param, "PWRNUC")
        old = read_row(lines, i)
        new = [0.0] * years + old[:len(old) - years]
        write_row(lines, i, new)


def carbon_price(year):
    if year < 2026:
        return 0.0
    return PRICE_2026 + (PRICE_2050 - PRICE_2026) * (year - 2026) / (2050 - 2026)


def use_price_policy(lines):
    """Remove the emission cap and add a carbon price."""
    i = find_row(lines, "AnnualEmissionLimit", "CO2_EQ")
    write_row(lines, i, [99999999] * len(YEARS))
    for i in range(len(lines)):
        if lines[i].startswith("param EmissionsPenalty"):
            prices = [carbon_price(y) for y in YEARS]
            lines.insert(i + 1, "[RE1,*,*]:")
            lines.insert(i + 2, " ".join(str(y) for y in YEARS) + " :=")
            lines.insert(i + 3, "CO2_EQ " + " ".join("%.10g" % p for p in prices))
            return


def make_data(policy, future):
    with open(DATA_FILE) as f:
        lines = f.read().split("\n")
    if policy == "price":
        use_price_policy(lines)
    if future is not None:
        change_demand(lines, future["demand_2050"])
        change_gas_price(lines, future["gas_price"])
        change_renewable_build(lines, future["renewable_build"])
        if future["nuclear_delay"] > 0:
            delay_nuclear(lines, future["nuclear_delay"])
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Solve and read the solution
# ----------------------------------------------------------------------------
def solve(data_text):
    os.makedirs("temp", exist_ok=True)
    data_file = os.path.abspath("temp/data.txt")
    lp_file = os.path.abspath("temp/model.lp")
    solution_file = os.path.abspath("temp/solution.txt")
    with open(data_file, "w") as f:
        f.write(data_text)
    if os.path.exists(solution_file):
        os.remove(solution_file)

    # run each solver from its own folder
    glpsol_folder = os.path.dirname(GLPSOL) or None
    cbc_folder = os.path.dirname(CBC) or None
    subprocess.run([GLPSOL, "--check", "-m", os.path.abspath(MODEL_FILE), "-d", data_file, "--wlp", lp_file],
                   capture_output=True, cwd=glpsol_folder)
    subprocess.run([CBC, lp_file, "solve", "-solu", solution_file], capture_output=True, cwd=cbc_folder)

    with open(solution_file) as f:
        lines = f.readlines()
    first = lines[0]
    if not first.startswith("Optimal"):
        return {"status": "infeasible"}

    result = {"status": "optimal", "objective": float(first.split()[-1])}
    capacity = {}
    co2 = {}
    for line in lines[1:]:
        words = line.replace("**", "").split()
        name = words[1]                      # e.g. TotalCapacityAnnual(RE1,PWRNUC,2050)
        value = float(words[2])
        if name.startswith("TotalCapacityAnnual("):
            region, tech, year = name[len("TotalCapacityAnnual("):-1].split(",")
            capacity[(tech, int(year))] = value
        if name.startswith("AnnualTechnologyEmission("):
            region, tech, emission, year = name[len("AnnualTechnologyEmission("):-1].split(",")
            co2[int(year)] = co2.get(int(year), 0.0) + value

    for y in YEARS:
        result["co2_%d" % y] = co2.get(y, 0.0)
        for group in GROUPS:
            total = 0.0
            for tech in GROUPS[group]:
                total += capacity.get((tech, y), 0.0)
            result["%s_%d" % (group, y)] = total
    result["co2_total"] = sum(co2.values())
    return result


def system_cost(result, policy):
    """Objective minus what is paid for emitting.
    Discounted like the objective: 5 % per year, middle of the year. Million EUR."""
    payments = 0.0
    if policy == "price":
        for y in YEARS:
            payments += carbon_price(y) * result["co2_%d" % y] / 1.05 ** (y - 2023 + 0.5)
    return result["objective"] - payments


# ----------------------------------------------------------------------------
# The experiment
# ----------------------------------------------------------------------------
def make_futures():
    rng = np.random.default_rng(SEED)
    futures = []
    for n in range(N_FUTURES):
        futures.append({
            "demand_2050": rng.uniform(DEMAND_2050[0], DEMAND_2050[1]),
            "gas_price": rng.uniform(GAS_PRICE[0], GAS_PRICE[1]),
            "renewable_build": rng.uniform(RENEWABLE_BUILD[0], RENEWABLE_BUILD[1]),
            "nuclear_delay": int(rng.integers(NUCLEAR_DELAY[0], NUCLEAR_DELAY[1] + 1)),
        })
    return futures


def check():
    result = solve(make_data("cap", None))
    print("Original case: objective %.5f, MUIO: %.5f" % (result["objective"], MUIO_OBJECTIVE))
    base = {"demand_2050": 1.0, "gas_price": 1.0, "renewable_build": 1.0, "nuclear_delay": 0} #tests if the mmodel work when introducing the random changing functions
    result = solve(make_data("cap", base))
    print("Same case through the experiment code: objective %.5f" % result["objective"])
    result = solve(make_data("price", base)) #tests if the price policy runs
    print("Price policy, original future: objective %.3f" % result["objective"])


def run_all():
    columns = ["future", "policy", "demand_2050", "gas_price", "renewable_build", "nuclear_delay",
               "status", "objective", "system_cost", "co2_total"]
    for y in YEARS:
        columns.append("co2_%d" % y)
        for group in GROUPS:
            columns.append("%s_%d" % (group, y))

    futures = make_futures()
    with open(RESULTS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for policy in ["cap", "price"]:
            for n in range(len(futures)):
                result = solve(make_data(policy, futures[n]))
                row = {"future": n, "policy": policy}
                row.update(futures[n])
                row.update(result)
                if result["status"] == "optimal":
                    row["system_cost"] = system_cost(result, policy)
                writer.writerow(row)
                print(policy, n, result["status"])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check()
    else:
        run_all()
