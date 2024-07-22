# Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
from dataclasses import dataclass, is_dataclass
from pathlib import Path
from typing import Optional

import torch
from eval_utils.evaluation.util import format_results
from eval_utils.evaluator import SLURPEvaluator
from eval_utils.inference import InferenceConfig, run_inference
from jiwer.measures import cer, wer
from omegaconf import MISSING, OmegaConf, open_dict

from nemo.core.config import hydra_runner
from nemo.utils import logging


@dataclass
class EvaluationConfig(InferenceConfig):
    dataset_manifest: str = MISSING
    output_filename: Optional[str] = "evaluation_transcripts.json"
    average: str = "micro"
    full: bool = False
    errors: bool = False
    table_layout: str = "fancy_grid"
    only_score_manifest: bool = False


@hydra_runner(config_name="EvaluationConfig", schema=EvaluationConfig)
def main(cfg: EvaluationConfig):
    torch.set_grad_enabled(False)

    cfg.output_filename = str(Path(Path(cfg.model_path).parent) / Path("predictions.json"))

    if is_dataclass(cfg):
        cfg = OmegaConf.structured(cfg)

    if cfg.audio_dir is not None:
        raise RuntimeError(
            "Evaluation script requires ground truth labels to be passed via a manifest file. "
            "If manifest file is available, submit it via `dataset_manifest` argument."
        )

    if not os.path.exists(cfg.dataset_manifest):
        raise FileNotFoundError(f"The dataset manifest file could not be found at path : {cfg.dataset_manifest}")

    if not cfg.only_score_manifest:
        # Transcribe speech into an output directory
        transcription_cfg = run_inference(cfg)  # type: EvaluationConfig

        # Release GPU memory if it was used during transcription
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        logging.info("Finished transcribing speech dataset. Computing metrics..")

    else:
        cfg.output_filename = cfg.dataset_manifest
        transcription_cfg = cfg

    ground_truth_text = []
    predicted_text = []
    invalid_manifest = False
    transcripts = []
    with open(transcription_cfg.output_filename, 'r') as f:
        for line in f:
            data = json.loads(line)

            if 'pred_text' not in data:
                invalid_manifest = True
                break

            ground_truth_text.append(data['text'].lower())
            predicted_text.append(data['pred_text'].lower())
            transcripts.append(data['transcript'])

    # Test for invalid manifest supplied
    if invalid_manifest:
        raise ValueError(
            f"Invalid manifest provided: {transcription_cfg.output_filename} does not "
            f"contain value for `pred_text`."
        )

    # Compute the metrics
    cer_score = cer(truth=ground_truth_text, hypothesis=predicted_text)
    wer_score = wer(truth=ground_truth_text, hypothesis=predicted_text)
    print(f"CER: {cer_score}")
    print(f"WER: {wer_score}")


if __name__ == '__main__':
    main()  # noqa pylint: disable=no-value-for-parameter
