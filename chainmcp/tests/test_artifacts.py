"""Artifact/deployment loading — pure filesystem, no chain."""

from __future__ import annotations

import json

import pytest

from chainmcp.artifacts import find_contracts_dir, load_deployment


def test_load_deployment_reads_the_deploy_scripts_artifact(tmp_path):
    """The docs/03 §2.4 shape, read from the location `just deploy-local` writes."""
    contracts = tmp_path / "contracts"
    (contracts / "deployments").mkdir(parents=True)
    (contracts / "foundry.toml").write_text("[profile.default]\n")
    artifact = {
        "v": 0,
        "chainId": 31337,
        "MockTOK": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
        "A2ASettlement": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    }
    (contracts / "deployments" / "anvil.json").write_text(json.dumps(artifact))

    assert load_deployment(contracts) == artifact


def test_find_contracts_dir_walks_up_to_foundry_root(tmp_path):
    contracts = tmp_path / "contracts"
    deep = tmp_path / "some" / "nested" / "dir"
    deep.mkdir(parents=True)
    contracts.mkdir()
    (contracts / "foundry.toml").write_text("[profile.default]\n")

    assert find_contracts_dir(start=deep) == contracts


def test_find_contracts_dir_raises_beyond_any_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_contracts_dir(start=tmp_path)
