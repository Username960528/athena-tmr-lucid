import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from muse_tmr.annotations import RemAnnotation, export_rem_annotations
from muse_tmr.cli.main import main
from muse_tmr.models import (
    PersonalRemClassifierConfig,
    PersonalRemModel,
    train_personal_rem_classifier,
)

TEST_FEATURES = (
    "p_rem",
    "feature_score_eye_movement_proxy",
    "feature_score_stillness",
)


def annotation(label, index, recording_id, *, p_rem, eye_score, stillness_score):
    return RemAnnotation(
        recording_id=recording_id,
        epoch_index=index,
        start_time=1000.0 + 30.0 * index,
        end_time=1030.0 + 30.0 * index,
        duration_seconds=30.0,
        label=label,
        p_rem=p_rem,
        feature_scores={
            "eye_movement_proxy": eye_score,
            "stillness": stillness_score,
        },
        prediction_source="heuristic",
    )


def labeled_rows():
    rows = []
    index = 0
    for recording_id in ("night-a", "night-b"):
        for offset in range(4):
            rows.append(
                annotation(
                    "probable_rem",
                    index,
                    recording_id,
                    p_rem=0.78 + offset * 0.03,
                    eye_score=0.80 + offset * 0.02,
                    stillness_score=0.85 + offset * 0.02,
                )
            )
            index += 1
        for offset in range(4):
            rows.append(
                annotation(
                    "wake" if offset % 2 == 0 else "nrem",
                    index,
                    recording_id,
                    p_rem=0.10 + offset * 0.03,
                    eye_score=0.05 + offset * 0.02,
                    stillness_score=0.15 + offset * 0.03,
                )
            )
            index += 1
    return tuple(rows)


def test_config():
    return PersonalRemClassifierConfig(
        feature_names=TEST_FEATURES,
        learning_rate=0.10,
        epochs=800,
        l2_penalty=0.0,
        min_training_rows=4,
    )


class TestPersonalRemClassifier(unittest.TestCase):
    def test_train_predicts_rem_like_rows_higher_than_wake_rows(self):
        model = train_personal_rem_classifier(labeled_rows(), config=test_config())

        rem_prediction = model.predict_mapping(
            annotation(
                "unknown",
                100,
                "night-c",
                p_rem=0.86,
                eye_score=0.88,
                stillness_score=0.91,
            ).to_training_dict()
        )
        wake_prediction = model.predict_mapping(
            annotation(
                "unknown",
                101,
                "night-c",
                p_rem=0.12,
                eye_score=0.04,
                stillness_score=0.20,
            ).to_training_dict()
        )

        self.assertEqual(rem_prediction.source, "personal")
        self.assertGreater(rem_prediction.probability, 0.70)
        self.assertLess(wake_prediction.probability, 0.30)
        self.assertIn("personal_model_positive", rem_prediction.reason_codes)
        self.assertFalse(hasattr(rem_prediction, "should_play"))

    def test_unknown_labels_are_skipped_and_missing_features_are_imputed(self):
        unknown = annotation(
            "unknown",
            999,
            "night-x",
            p_rem=0.99,
            eye_score=1.0,
            stillness_score=1.0,
        )
        model = train_personal_rem_classifier(labeled_rows() + (unknown,), config=test_config())

        prediction = model.predict_mapping({"p_rem": 0.8, "feature_score_eye_movement_proxy": 0.9})

        self.assertEqual(model.training_summary.skipped_unknown_rows, 1)
        self.assertIn("missing_features_imputed", prediction.reason_codes)

    def test_requires_both_positive_and_negative_labels(self):
        positive_only = tuple(row for row in labeled_rows() if row.label == "probable_rem")

        with self.assertRaises(ValueError):
            train_personal_rem_classifier(positive_only, config=test_config())

    def test_model_artifact_roundtrip_preserves_predictions_and_metrics(self):
        model = train_personal_rem_classifier(labeled_rows(), config=test_config())
        row = labeled_rows()[0].to_training_dict()

        with tempfile.TemporaryDirectory() as tmp:
            model_path = model.save(Path(tmp) / "personal_rem_model.json")
            loaded = PersonalRemModel.load(model_path)
            payload = json.loads(model_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["model_version"], 1)
        self.assertEqual(loaded.feature_names, TEST_FEATURES)
        self.assertIn("feature_importance", payload)
        self.assertIn("calibration_bins", payload["training_summary"]["metrics"])
        self.assertEqual(
            payload["training_summary"]["group_holdout_metrics"]["status"],
            "computed",
        )
        self.assertAlmostEqual(
            model.predict_mapping(row).probability,
            loaded.predict_mapping(row).probability,
            places=9,
        )

    def test_cli_trains_and_saves_personal_classifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            annotations_path = export_rem_annotations(labeled_rows(), tmp_path / "labels.csv")
            model_path = tmp_path / "model.json"

            with redirect_stdout(io.StringIO()):
                exit_code = main([
                    "train-rem-classifier",
                    str(annotations_path),
                    "--output",
                    str(model_path),
                    "--feature",
                    "p_rem",
                    "--feature",
                    "feature_score_eye_movement_proxy",
                    "--feature",
                    "feature_score_stillness",
                    "--epochs",
                    "800",
                ])

            payload = json.loads(model_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["model_type"], "balanced_logistic_regression")
        self.assertEqual(payload["training_summary"]["training_rows"], 16)


if __name__ == "__main__":
    unittest.main()
