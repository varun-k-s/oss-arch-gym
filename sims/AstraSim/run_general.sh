#! /bin/bash -v

# Absolue path to this script
SCRIPT_DIR=$(dirname "$(realpath $0)")

# Absolute paths to useful directories
BINARY="${SCRIPT_DIR:?}"/astrasim-archgym/astra-sim/build/astra_analytical/build/AnalyticalAstra/bin/AnalyticalAstra
SYSTEM="${SCRIPT_DIR:?}"/general_system.txt
NETWORK="${SCRIPT_DIR:?}"/general_network.json
WORKLOAD="${SCRIPT_DIR:?}"/astrasim-archgym/themis/inputs/workload/$3

echo "SH NETWORK: ${NETWORK}"
echo "SH SYSTEM: ${SYSTEM}"
echo "SH WORKLOAD: ${WORKLOAD}"

STATS="${SCRIPT_DIR:?}"/results/run_general

rm -rf "${STATS}"
mkdir "${STATS}"

"${BINARY}" \
--network-configuration="${NETWORK}" \
--system-configuration="${SYSTEM}" \
--workload-configuration="${WORKLOAD}" \
--path="${STATS}/" \
--run-name="sample_all_reduce" \

