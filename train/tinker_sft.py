"""LoRA fine-tune on Tinker: teach a small open model to speak as the crew and stay grounded.

Needs TINKER_API_KEY. Run from the repo root after make_sft.py:
  python train/tinker_sft.py train/out
"""
import asyncio
import os
import sys

import chz
from tinker_cookbook.renderers import TrainOnWhat
from tinker_cookbook.supervised import train
from tinker_cookbook.supervised.data import FromConversationFileBuilder
from tinker_cookbook.supervised.types import ChatDatasetBuilderCommonConfig

MODEL = os.environ.get("WH_TINKER_MODEL", "Qwen/Qwen3-8B")
RENDERER = os.environ.get("WH_TINKER_RENDERER", "qwen3_disable_thinking")


def config(out_dir: str):
    common = ChatDatasetBuilderCommonConfig(
        model_name_for_tokenizer=MODEL,
        renderer_name=RENDERER,
        max_length=3072,
        batch_size=4,
        train_on_what=TrainOnWhat.LAST_ASSISTANT_MESSAGE,
    )
    dataset = FromConversationFileBuilder(common_config=common, file_path=f"{out_dir}/sft_train.jsonl", test_size=0)
    return chz.Blueprint(train.Config).apply({
        "log_path": f"{out_dir}/run",
        "model_name": MODEL,
        "recipe_name": "witching_hour_crew",
        "renderer_name": RENDERER,
        "dataset_builder": dataset,
        "learning_rate": 2e-4,
        "lr_schedule": "linear",
        "num_epochs": 3,
        "lora_rank": 16,
        "save_every": 1000,
    }).make()


if __name__ == "__main__":
    asyncio.run(train.main(config(sys.argv[1] if len(sys.argv) > 1 else "train/out")))
