# Build reopt_sysimage.so from the main julia_src project, traced with
# sysimage/workload.jl.
#
# Run from the julia_src directory:
#   julia --project=sysimage sysimage/build.jl
#
# Output: julia_src/reopt_sysimage.so
#
# Runtime then starts Julia with:
#   julia --sysimage=/opt/julia_src/reopt_sysimage.so --project=/opt/julia_src ...

using PackageCompiler

const JULIA_SRC = abspath(joinpath(@__DIR__, ".."))
const OUTPUT    = joinpath(JULIA_SRC, "reopt_sysimage.so")
const WORKLOAD  = joinpath(@__DIR__, "workload.jl")

# Packages to bake into the sysimage. Mirrors the imports at the top of http.jl
# plus the solvers loaded in os_solvers.jl. Xpress is left out — it's only
# loaded when XPRESS_INSTALLED=True and the licence file is mounted, so it's
# not part of the base image.
const PACKAGES = [
    :AxisArrays,
    :HTTP,
    :JSON,
    :JuMP,
    :MathOptInterface,
    :MutableArithmetics,
    :REopt,
    :GhpGhx,
    :HiGHS,
    :Cbc,
    :SCIP,
]

@info "Building sysimage" julia_src=JULIA_SRC output=OUTPUT n_packages=length(PACKAGES)

create_sysimage(
    PACKAGES;
    sysimage_path = OUTPUT,
    project = JULIA_SRC,
    precompile_execution_file = WORKLOAD,
    incremental = true,
)

@info "Sysimage built" size_mb=round(filesize(OUTPUT) / 1024 / 1024, digits=1)
