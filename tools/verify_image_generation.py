"""Opt-in live generation/edit gate with content-free diagnostics."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.cloud_errors import CloudInferenceError
from app.inference.completion import IncompleteResponseError
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.settings.cloud import load_cloud_config


def verify(output, key_file):
    # No environment/file mutation and no secret included in reports or errors.
    lines = key_file.read_text(encoding="utf-8-sig").splitlines()
    key = lines[0].strip() if lines else ""
    report = {"generation": "not_run", "restart": "not_run", "edit": "not_run", "passed": False}
    config = load_cloud_config()
    config = config.model_copy(update={"image_generation": config.image_generation.model_copy(update={"quality": "low"})})
    report.update(cloud_model=config.default_model, image_model=config.image_generation.model, quality="low")
    output.mkdir(parents=True, exist_ok=True)
    engine = OpenAIResponsesInferenceEngine(config, api_key=key)
    service = ConversationService(engine, ConversationStore(output / "chat.json"))
    stage = "generation"
    try:
        first = service.run("Generate one simple image of a blue circle on a charcoal background.")
        assert first.generated_images
        report["generation"] = "passed"
        report["image_count"] = len(first.generated_images)
        original_ids = [ref.id for ref in first.generated_images]
        service.shutdown()
        stage = "restart"
        engine = OpenAIResponsesInferenceEngine(config, api_key=key)
        service = ConversationService(engine, ConversationStore(output / "chat.json"))
        originals = service.store.visible_messages()[-1].generated_images
        assert [ref.id for ref in originals] == original_ids
        for ref in originals:
            service.store.attachment_store.verify(ref)
        report["restart"] = "passed"
        stage = "edit"
        second = service.run("Make the background darker, preserving the blue circle.")
        assert second.generated_images
        report["edit"] = "passed"
        report["passed"] = True
    except CloudInferenceError as exc:
        report[stage] = "failed"
        report["error_category"] = exc.code.value
    except IncompleteResponseError as exc:
        report[stage] = "failed"
        report["error_category"] = exc.completion.failure_reason
    except Exception:
        report[stage] = "failed"
        report["error_category"] = "verification_failed"
    finally:
        if report["generation"] != "passed":
            report["edit"] = "skipped_no_generated_source"
            report["restart"] = "skipped_no_generated_source"
        elif report["restart"] != "passed":
            report["edit"] = "skipped_restart_failed"
        runner = engine._runner
        service.shutdown()
        report["transport_released"] = runner is None or runner._thread is None or not runner._thread.is_alive()
        report["passed"] = all(report[item] == "passed" for item in ("generation", "restart", "edit")) and report["transport_released"]
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("state/image-generation-live"))
    args = parser.parse_args()
    report = verify(args.output, args.key_file)
    print(json.dumps(report))
    raise SystemExit(0 if report["passed"] else 1)
