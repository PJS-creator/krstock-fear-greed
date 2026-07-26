import json

from scripts.update_meta_strategy import main


def test_script_records_configuration_failure_without_overwriting_signal(tmp_path, monkeypatch):
    monkeypatch.delenv("TIINGO_API_TOKEN", raising=False)
    output = tmp_path / "data"

    exit_code = main(
        [
            "--output-root",
            str(output),
            "--audit-dir",
            str(tmp_path / "audit"),
            "--run-slot",
            "manual",
            "--now",
            "2026-07-26T00:00:00Z",
        ]
    )

    run = json.loads((output / "runs" / "latest_run.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert run["status"] == "CONFIG_FAILED"
    assert not (output / "signals" / "latest_validated.json").exists()
