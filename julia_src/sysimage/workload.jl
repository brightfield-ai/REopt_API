# Tracing workload used by PackageCompiler to produce reopt_sysimage.so.
#
# Goal: exercise every code path that runs on the first request after a
# container starts. Anything compiled here gets baked into the sysimage and
# doesn't need JIT specialization at runtime.
#
# Keep the workload small but representative — one tiny LP, one tiny MIP per
# supported solver. Bigger workloads = bigger sysimage and slower CI build,
# without dramatic runtime gain.

using JuMP
using HiGHS
using Cbc
using SCIP
using HTTP
using JSON

function _tiny_lp(optimizer)
    m = Model(optimizer)
    set_silent(m)
    @variable(m, x >= 0)
    @variable(m, y >= 0)
    @constraint(m, x + 2y >= 3)
    @objective(m, Min, x + y)
    optimize!(m)
    return objective_value(m)
end

function _tiny_mip(optimizer)
    m = Model(optimizer)
    set_silent(m)
    @variable(m, x >= 0, Int)
    @variable(m, y >= 0)
    @constraint(m, x + y >= 1.5)
    @objective(m, Min, x + y)
    optimize!(m)
    return objective_value(m)
end

# HiGHS — the default solver in REopt. Highest-priority trace.
_tiny_lp(HiGHS.Optimizer)
_tiny_mip(HiGHS.Optimizer)

# Cbc — MIP only, no LP solve to keep the trace minimal.
_tiny_mip(Cbc.Optimizer)

# SCIP — MIP only, same reason.
_tiny_mip(SCIP.Optimizer)

# Exercise JSON round-trip used by every HTTP handler — cheap but covers
# JSON.parse + JSON.json specialization on Dict{String,Any}.
let payload = JSON.json(Dict("a" => 1, "b" => [1.0, 2.0], "c" => "x"))
    JSON.parse(payload)
end
