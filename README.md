# gossip-reachability
Reachability analysis of gossip protocols


Replicates and extends reachability results for five gossip protocols (ANY, CO, LNS, TOK, SPI). 
Phase 1: replicate counts for n=2..4 (Table 1).  
Phase 2: extend counts to n=5..9 with pruning + canonicalisation (TODO).  
Phase 3: propose Adaptive Token (ATK) variant; analyse inclusion relations.

## Quick Start
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest
python -m src.enumerator
