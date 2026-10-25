# External data for Stage 3

Repo `data/` is gitignored. Stage 3 expects BattLeDIM files under `data/raw/`.

Already present in a typical Ripple checkout: pressures, flows, levels, `L-TOWN.inp`.

**Also required** (downloaded from Zenodo [4017659](https://zenodo.org/records/4017659) if missing):

```bash
cd data/raw
curl -L -o 2018_SCADA_Demands.csv \
  https://zenodo.org/api/records/4017659/files/2018_SCADA_Demands.csv/content
# optional diagnostic labels (not used in fitting):
curl -L -o 2018_Leakages.csv \
  https://zenodo.org/api/records/4017659/files/2018_Leakages.csv/content
```

Expected MD5 for `2018_SCADA_Demands.csv`: `8803afcb1da2428de169237be3d911fb`.
