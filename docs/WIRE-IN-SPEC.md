# REopt Julia Solver — Wire-In Spec

> **Base URL:** `https://reopt-julia-77008123735.us-central1.run.app`
>
> **Transport:** HTTPS / JSON — all request and response bodies are `application/json`.
>
> **Auth:** None (unauthenticated Cloud Run service). An optional `api_key` field
> can be passed inside the `/reopt` request body to override the server-side
> NREL Developer API key used for NREL data lookups (PVWatts, URDB, AVERT, etc.).

---

## Table of Contents

1. [Health Check](#1-health-check)
2. [Run REopt Optimization](#2-run-reopt-optimization) — the primary endpoint
3. [Energy Resilience (ERP)](#3-energy-resilience-erp)
4. [GHPGHX (Ground-Source Heat Pump)](#4-ghpghx)
5. [Simulated Load Profiles](#5-simulated-load-profiles)
6. [Lookup / Defaults Endpoints](#6-lookup--defaults-endpoints)
7. [Error Handling](#7-error-handling)
8. [Timeout & Performance Notes](#8-timeout--performance-notes)

---

## 1. Health Check

```
GET /health
```

**Response** `200 OK`

```json
{ "Julia-api": "healthy!" }
```

Use this to verify the service is warm and accepting requests. Cold starts
on Cloud Run can take 60–90 s while Julia precompiles.

---

## 2. Run REopt Optimization

```
POST /reopt
Content-Type: application/json
```

This is the main endpoint. It runs the REopt mixed-integer linear program and
returns optimal sizing, dispatch, and financial results.

### 2.1 Minimal Request

The smallest valid payload requires **four top-level keys**:

```json
{
  "Settings": {
    "solver_name": "HiGHS",
    "timeout_seconds": 420,
    "optimality_tolerance": 0.01,
    "run_bau": true
  },
  "Site": {
    "latitude": 34.58,
    "longitude": -118.12
  },
  "ElectricLoad": {
    "doe_reference_name": "RetailStore",
    "annual_kwh": 1000000,
    "year": 2022
  },
  "ElectricTariff": {
    "urdb_label": "5ed6c1a15457a3367add15ae"
  }
}
```

> **Required fields inside `Settings`:** `timeout_seconds`, `optimality_tolerance`, `run_bau`.
> The server pops these before forwarding to REopt.jl.

### 2.2 Full Input Schema (all top-level keys)

Every key below is **optional** except the four marked ★. Include a key only
when you want that technology or load type considered in the optimization.

| Key                    | Required | Purpose                                                |
| ---------------------- | -------- | ------------------------------------------------------ |
| **`Settings`** ★       | Yes      | Solver config (solver name, timeout, tolerance, BAU)   |
| **`Site`** ★           | Yes      | Location (`latitude`, `longitude`) + land/roof limits  |
| **`ElectricLoad`** ★   | Yes      | Building electric load profile or DOE reference name   |
| **`ElectricTariff`** ★ | Yes      | Utility rate (URDB label, blended rate, or TOU array)  |
| `Financial`            | No       | Discount rates, tax rates, analysis period, escalation |
| `ElectricUtility`      | No       | Grid emissions factors, outage parameters              |
| `PV`                   | No       | Photovoltaic system (cost, tilt, module type, etc.)    |
| `Wind`                 | No       | Wind turbine parameters                                |
| `ElectricStorage`      | No       | Battery storage                                        |
| `Generator`            | No       | Diesel / gas generator                                 |
| `Boiler`               | No       | New boiler                                             |
| `ExistingBoiler`       | No       | Existing on-site boiler                                |
| `CHP`                  | No       | Combined heat & power                                  |
| `SteamTurbine`         | No       | Steam turbine                                          |
| `ElectricHeater`       | No       | Electric heater                                        |
| `ASHPSpaceHeater`      | No       | Air-source heat pump (space heating)                   |
| `ASHPWaterHeater`      | No       | Air-source heat pump (water heating)                   |
| `GHP`                  | No       | Ground-source (geothermal) heat pump                   |
| `CST`                  | No       | Concentrating solar thermal                            |
| `ColdThermalStorage`   | No       | Chilled water thermal storage                          |
| `HotThermalStorage`    | No       | Hot water thermal storage                              |
| `HighTempThermalStorage` | No     | High-temperature thermal storage                       |
| `SpaceHeatingLoad`     | No       | Space heating load profile                             |
| `DomesticHotWaterLoad` | No       | DHW load profile                                       |
| `ProcessHeatLoad`      | No       | Process heat load profile                              |
| `CoolingLoad`          | No       | Cooling load profile                                   |
| `Meta`                 | No       | Description / address metadata                         |
| `api_key`              | No       | Override the NREL Developer API key (string)           |

### 2.3 Key Input Objects — Detail

#### `Settings`

| Field                        | Type    | Default  | Notes                                      |
| ---------------------------- | ------- | -------- | ------------------------------------------ |
| `solver_name`                | string  | `HiGHS`  | `"HiGHS"`, `"Cbc"`, or `"SCIP"`           |
| `timeout_seconds`            | int     | —        | **Required.** Solver wall-clock limit (s)  |
| `optimality_tolerance`       | float   | —        | **Required.** MIP gap (e.g. `0.01` = 1%)  |
| `run_bau`                    | bool    | —        | **Required.** Run business-as-usual case?  |
| `time_steps_per_hour`        | int     | `1`      | `1` or `2` (hourly or half-hourly)         |
| `add_soc_incentive`          | bool    | `true`   | Add SOC incentive to objective              |
| `off_grid_flag`              | bool    | `false`  | Off-grid mode                              |
| `include_climate_in_objective` | bool  | `false`  | Include CO₂ cost in objective              |
| `include_health_in_objective`  | bool  | `false`  | Include health cost in objective           |

#### `Site`

| Field         | Type   | Notes                                  |
| ------------- | ------ | -------------------------------------- |
| `latitude`    | float  | **Required.** Decimal degrees          |
| `longitude`   | float  | **Required.** Decimal degrees          |
| `land_acres`  | float  | Available land for ground-mount PV     |
| `roof_squarefeet` | float | Available roof area for rooftop PV |
| `sector`      | string | `"commercial/industrial"`, `"residential"`, etc. |

#### `ElectricLoad`

Provide **one** of the following load specification methods:

| Method                 | Fields                                                      |
| ---------------------- | ----------------------------------------------------------- |
| DOE reference building | `doe_reference_name` + `annual_kwh` + `year`                |
| Custom 8760 profile    | `loads_kw` (array of 8760 floats) + `year`                  |
| Monthly totals + peaks | `monthly_totals_kwh` (12) + `monthly_peaks_kw` (12) + `year` |
| Blended buildings      | `blended_doe_reference_names` + `blended_doe_reference_percents` |

DOE reference names include: `"RetailStore"`, `"Hospital"`, `"LargeOffice"`,
`"SmallOffice"`, `"MidriseApartment"`, `"Warehouse"`, `"Supermarket"`, etc.

#### `ElectricTariff`

Provide **one** of:

| Method          | Fields                                                                 |
| --------------- | ---------------------------------------------------------------------- |
| URDB label      | `urdb_label` (string — from [URDB](https://openei.org/wiki/Utility_Rate_Database)) |
| Blended rate    | `blended_annual_energy_rate` + `blended_annual_demand_rate`            |
| TOU rates       | `tou_energy_rates_per_kwh` (8760 array)                               |
| Full URDB JSON  | `urdb_response` (complete URDB rate object)                            |

### 2.4 Response — `200 OK`

```json
{
  "results": {
    "status": "optimal",
    "Site": { ... },
    "Financial": { "lcc": 1234567.89, "npv": 234567.89, ... },
    "ElectricTariff": { ... },
    "ElectricUtility": { ... },
    "ElectricLoad": { ... },
    "PV": { "size_kw": 250.0, ... },
    "ElectricStorage": { "size_kw": 50.0, "size_kwh": 200.0, ... },
    ...
  },
  "reopt_version": "0.53.0",
  "inputs_with_defaults_set_in_julia": {
    "Financial": { ... },
    "ElectricUtility": { ... },
    ...
  }
}
```

Key fields in `results`:

| Path                          | Type   | Description                                |
| ----------------------------- | ------ | ------------------------------------------ |
| `results.status`              | string | `"optimal"`, `"infeasible"`, `"timed_out"`, `"error"` |
| `results.Financial.lcc`       | float  | Lifecycle cost ($)                         |
| `results.Financial.npv`       | float  | Net present value ($)                      |
| `results.PV.size_kw`          | float  | Optimal PV capacity (kW)                   |
| `results.ElectricStorage.size_kw` | float | Optimal battery power (kW)             |
| `results.ElectricStorage.size_kwh` | float | Optimal battery energy (kWh)          |
| `results.Wind.size_kw`        | float  | Optimal wind capacity (kW)                 |

`inputs_with_defaults_set_in_julia` returns any default values that Julia
set internally (e.g. emissions factors, financial defaults, technology costs).
Use this to audit what assumptions the model used.

### 2.5 Response — `400 Bad Request`

Returned when the model solves but with status `"error"` (e.g. infeasible
inputs):

```json
{
  "results": { "status": "error", ... },
  "reopt_version": "0.53.0",
  "inputs_with_defaults_set_in_julia": { ... }
}
```

### 2.6 Response — `500 Internal Server Error`

Returned on unhandled exceptions in Julia:

```json
{
  "error": "DomainError with -1.5: ...",
  "reopt_version": "0.53.0"
}
```

### 2.7 Worked Example — PV + Battery

```bash
curl -X POST https://reopt-julia-77008123735.us-central1.run.app/reopt \
  -H "Content-Type: application/json" \
  -d '{
    "Settings": {
      "solver_name": "HiGHS",
      "timeout_seconds": 420,
      "optimality_tolerance": 0.01,
      "run_bau": true
    },
    "Site": {
      "latitude": 34.58,
      "longitude": -118.12,
      "roof_squarefeet": 5000,
      "land_acres": 1.0
    },
    "ElectricLoad": {
      "doe_reference_name": "RetailStore",
      "annual_kwh": 10000000,
      "year": 2017
    },
    "ElectricTariff": {
      "urdb_label": "5ed6c1a15457a3367add15ae"
    },
    "Financial": {
      "analysis_years": 20,
      "offtaker_discount_rate_fraction": 0.081,
      "offtaker_tax_rate_fraction": 0.4,
      "om_cost_escalation_rate_fraction": 0.025,
      "elec_cost_escalation_rate_fraction": 0.026,
      "owner_discount_rate_fraction": 0.081,
      "owner_tax_rate_fraction": 0.4
    },
    "PV": {
      "installed_cost_per_kw": 2000,
      "om_cost_per_kw": 16,
      "macrs_option_years": 5,
      "macrs_bonus_fraction": 0.4,
      "federal_itc_fraction": 0.3,
      "tilt": 34.58,
      "azimuth": 180,
      "module_type": 0,
      "array_type": 1,
      "degradation_fraction": 0.005
    },
    "ElectricStorage": {
      "installed_cost_per_kw": 1000,
      "installed_cost_per_kwh": 500,
      "replace_cost_per_kw": 460,
      "replace_cost_per_kwh": 230,
      "macrs_option_years": 5,
      "macrs_bonus_fraction": 0.4,
      "can_grid_charge": true
    }
  }'
```

---

## 3. Energy Resilience (ERP)

```
POST /erp
Content-Type: application/json
```

Runs backup reliability / energy resilience analysis on a previously optimized
system.

### Request Body

Pass the ERP input dictionary directly. Key fields:

| Field                | Type    | Description                                     |
| -------------------- | ------- | ----------------------------------------------- |
| `ElectricStorage`    | object  | Battery parameters from REopt results            |
| `PV`                 | object  | PV parameters from REopt results                 |
| `Wind`               | object  | Wind parameters from REopt results               |
| `PrimeGenerator`     | object  | Generator parameters                             |
| `Outage`             | object  | Outage duration, start time step, etc.           |

### Response — `200 OK`

```json
{
  "reopt_version": "0.53.0",
  "mean_hours_of_survival": 48.5,
  "probability_of_survival": [ ... ],
  ...
}
```

---

## 4. GHPGHX

```
POST /ghpghx
Content-Type: application/json
```

Runs the GhpGhx ground-source heat pump / ground heat exchanger model.
Returns sizing results for use in REopt's `GHP` input.

### Response — `200 OK`

Returns `ghpghx_results` dictionary with thermal performance data for REopt
integration.

---

## 5. Simulated Load Profiles

```
POST /simulated_load
Content-Type: application/json
```

Generates simulated building load profiles from DOE Commercial Reference
Building (CRB) data.

### Request Body

| Field                        | Type          | Description                             |
| ---------------------------- | ------------- | --------------------------------------- |
| `doe_reference_name`         | string/array  | DOE building type(s)                    |
| `latitude`                   | float         | Site latitude                           |
| `longitude`                  | float         | Site longitude                          |
| `load_type`                  | string        | `"electric"`, `"heating"`, `"cooling"`  |
| `annual_kwh` (or `_mmbtu`, `_tonhour`) | float | Annual energy to scale to     |
| `percent_share`              | float[]       | Blend weights (if multiple buildings)   |
| `monthly_totals_kwh`         | float[12]     | Monthly energy totals                   |

### Response — `200 OK`

Returns the simulated load profile (8760 hourly values).

---

## 6. Lookup / Defaults Endpoints

All of these accept a JSON body via **GET** (unusual but that's how the
server is wired — send the body with a GET request, or use POST if your
HTTP client can't send bodies with GET).

### 6.1 CHP Defaults

```
GET /chp_defaults
```

| Field                              | Type   | Description                     |
| ---------------------------------- | ------ | ------------------------------- |
| `prime_mover`                      | string | `"recip_engine"`, `"micro_turbine"`, `"combustion_turbine"`, `"fuel_cell"`, `"steam_turbine"` |
| `hot_water_or_steam`               | string | `"hot_water"` or `"steam"`      |
| `avg_boiler_fuel_load_mmbtu_per_hour` | float | Average boiler fuel load      |
| `avg_electric_load_kw`             | float  | Average electric load           |
| `max_electric_load_kw`             | float  | Peak electric load              |
| `size_class`                       | int    | CHP size class (0–4)           |

### 6.2 Absorption Chiller Defaults

```
GET /absorption_chiller_defaults
```

| Field                                    | Type   |
| ---------------------------------------- | ------ |
| `thermal_consumption_hot_water_or_steam`  | string |
| `chp_prime_mover`                         | string |
| `boiler_type`                             | string |
| `load_max_tons`                           | float  |

### 6.3 AVERT Emissions Profile

```
GET /avert_emissions_profile
```

| Field      | Type  |
| ---------- | ----- |
| `latitude` | float |
| `longitude`| float |
| `load_year`| int   |

Returns hourly grid emissions factors (lb CO₂/SO₂/NOx/PM₂.₅ per kWh).

### 6.4 Cambium Emissions / Clean Energy Profile

```
GET /cambium_profile
```

| Field           | Type   |
| --------------- | ------ |
| `latitude`      | float  |
| `longitude`     | float  |
| `start_year`    | int    |
| `lifetime`      | int    |
| `load_year`     | int    |
| `scenario`      | string |
| `location_type` | string |
| `metric_col`    | string |
| `grid_level`    | string |

### 6.5 EASIUR Health Costs

```
GET /easiur_costs
```

| Field       | Type  |
| ----------- | ----- |
| `latitude`  | float |
| `longitude` | float |
| `inflation` | float |

Returns health-related emissions cost data ($/tonne for NOx, SO₂, PM₂.₅).

### 6.6 Sector Defaults

```
GET /sector_defaults
```

| Field                      | Type   |
| -------------------------- | ------ |
| `sector`                   | string |
| `federal_sector_state`     | string |
| `federal_procurement_type` | string |

### 6.7 Existing Chiller Default COP

```
GET /get_existing_chiller_default_cop
```

| Field                                           | Type  |
| ----------------------------------------------- | ----- |
| `existing_chiller_max_thermal_factor_on_peak_load` | float |
| `max_load_kw`                                    | float |
| `max_load_kw_thermal`                            | float |

### 6.8 ASHP Defaults

```
GET /get_ashp_defaults
```

| Field              | Type   | Default          |
| ------------------ | ------ | ---------------- |
| `load_served`      | string | `"SpaceHeating"` |
| `force_into_system`| bool   | `false`          |

### 6.9 PV Cost Defaults

```
GET /pv_cost_defaults
```

| Field                                     | Type   |
| ----------------------------------------- | ------ |
| `size_class`                              | int    |
| `electric_load_annual_kwh`                | float  |
| `site_land_acres`                         | float  |
| `site_roof_squarefeet`                    | float  |
| `min_kw` / `max_kw`                      | float  |
| `array_type`                              | int    |
| `location`                                | string |

Returns `installed_cost_per_kw`, `om_cost_per_kw`, `size_class`.

### 6.10 Load Metrics

```
GET /get_load_metrics
```

| Field           | Type     | Description           |
| --------------- | -------- | --------------------- |
| `load_profile`  | float[]  | 8760 hourly load (kW) |

Returns `max_kw`, `annual_kwh`, `monthly_totals_kwh`, `monthly_peaks_kw`.

### 6.11 GHP Efficiency Thermal Factors

```
GET /ghp_efficiency_thermal_factors
```

| Field                | Type   |
| -------------------- | ------ |
| `latitude`           | float  |
| `longitude`          | float  |
| `doe_reference_name` | string |

### 6.12 Ground Conductivity

```
GET /ground_conductivity
```

| Field       | Type  |
| ----------- | ----- |
| `latitude`  | float |
| `longitude` | float |

Returns `climate_zone`, `nearest_city`, `thermal_conductivity`.

---

## 7. Error Handling

| HTTP Code | Meaning                          | Body Shape                                  |
| --------- | -------------------------------- | ------------------------------------------- |
| `200`     | Success                          | Endpoint-specific JSON                      |
| `400`     | Model error / invalid inputs     | `{ "results": { "status": "error" }, ... }` or `{ "error": "..." }` |
| `500`     | Unhandled Julia exception        | `{ "error": "...", "reopt_version": "..." }` |

All error responses include a human-readable `error` string. The `/reopt`
endpoint additionally includes `reopt_version` in every response.

---

## 8. Timeout & Performance Notes

- **Cold start:** The Julia container takes 60–90 seconds to start on Cloud Run
  (JIT compilation). The health endpoint warms up quickly; `/reopt` triggers
  full precompilation on first call.
- **Solver timeout:** Controlled by `Settings.timeout_seconds`. Recommended:
  `300`–`600` for complex cases. The Cloud Run request timeout is set to
  `900s`.
- **Concurrency:** The service is configured for `concurrency=4` per instance
  with 4 CPU / 8 GiB RAM.
- **Scaling:** `min_instances=0`, `max_instances=10`. Set `min_instances=1` if
  you need to avoid cold starts.
- **Large payloads:** Custom 8760 load profiles add ~70 KB to the request.
  This is fine — there is no payload size limit on the service.

---

## Quick-Start Checklist

1. **Verify the service is up:**
   ```bash
   curl https://reopt-julia-77008123735.us-central1.run.app/health
   ```

2. **Run a minimal optimization:**
   ```bash
   curl -X POST .../reopt -H "Content-Type: application/json" -d '{
     "Settings": { "solver_name":"HiGHS", "timeout_seconds":420, "optimality_tolerance":0.01, "run_bau":true },
     "Site": { "latitude":40.7128, "longitude":-74.0060 },
     "ElectricLoad": { "doe_reference_name":"LargeOffice", "annual_kwh":5000000, "year":2022 },
     "ElectricTariff": { "blended_annual_energy_rate":0.10, "blended_annual_demand_rate":20.0 }
   }'
   ```

3. **Check the response:**
   - `results.status` → `"optimal"` means success
   - `results.Financial.npv` → net present value of recommended system
   - Technology keys (`PV`, `ElectricStorage`, etc.) → optimal sizes

4. **Add technologies** to the input to let the optimizer consider them
   (PV, Wind, Battery, CHP, etc.). If a technology key is absent, that
   technology is not considered.
