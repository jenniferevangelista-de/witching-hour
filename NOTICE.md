# Third-party notices

## TabPFN (Prior Labs)

**Built with PriorLabs-TabPFN.**

Witching Hour uses the TabPFN v2 regressor weights published by Prior Labs at
https://huggingface.co/Prior-Labs/TabPFN-v2-reg, through the `tabpfn` Python package
(https://github.com/PriorLabs/TabPFN). The weights are not included in this repository;
they are downloaded by the `tabpfn` package on first use.

The weights are licensed under the Prior Labs License 1.1 (Apache 2.0 plus an attribution
clause): https://priorlabs.ai/tabpfn-license. A copy of that license is in
`licenses/PRIOR_LABS_LICENSE.txt`.

Hollmann, N., Müller, S., Purucker, L. et al. Accurate predictions on small data with a tabular
foundation model. Nature 637, 319–326 (2025). https://doi.org/10.1038/s41586-024-08328-6

## Gemma (Google)

The narrators and the investigator agent run Gemma 4 (`gemma4:e4b` by default) locally through
Ollama. Gemma 4 weights are released under the Apache 2.0 license:
https://huggingface.co/google/gemma-4-E4B-it. Weights are not included in this repository.

## Data: Appliances energy prediction (UCI)

Candanedo, L. M., Feldheim, V., & Deramaix, D. (2017). Data driven prediction models of energy use
of appliances in a low-energy house. Energy and Buildings, 140, 81–97.
https://doi.org/10.1016/j.enbuild.2017.01.083

Dataset: https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction, licensed CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). The `demo_data/` folder contains derived values
(per-night readings and model predictions) computed from this dataset.

## Fonts

The web page loads Creepster and Inter from Google Fonts (SIL Open Font License 1.1).
