#!/bin/bash
# PCBWorld engine build: environment.yml pins no nng version, conda-forge gave nng 2.0.0, whose headers dropped
# nng/protocol/reqrep0/rep.h (KiCad's kinng expects nng 1.x). Downgrade to nng 1.x and rebuild.
set -x
cd ~/pcbworld
source ~/miniforge3/etc/profile.d/conda.sh
conda activate pcbworld
conda install -y -c conda-forge "nng<2" 2>&1 | tail -3
ls $CONDA_PREFIX/include/nng/protocol/reqrep0/rep.h
export BUILD_DIR=$HOME/pcbworld/build_rl
time bash engine/build_rl_router.sh 2>&1 | tail -30
export PYTHONPATH=build_rl/pcbnew/python/rl:.
python -c "import kicad_rl_router; print('kicad_rl_router OK', kicad_rl_router.__file__)"
echo FIX2_DONE
