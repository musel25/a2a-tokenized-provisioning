// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Script} from "forge-std/Script.sol";
import {A2ASettlement} from "../src/Settlement.sol";
import {MockTOK} from "../src/MockTOK.sol";

/// The real deploy (M1.4): MockTOK + A2ASettlement onto a running Anvil, addresses
/// written to `contracts/deployments/anvil.json` — the one artifact every Python
/// package reads to find the chain (docs/03 §2.4; chainmcp consumes it at M1.5).
/// (Repo root was the first choice, but Foundry hard-denies fs writes above its root.)
///
/// MockTOK deploys FIRST, on purpose: a fresh chain's contract addresses depend only on
/// (deployer, nonce), so deploy[0] from anvil account #0 always lands at 0x5FbD…0aa3 —
/// the address `a2a_interfaces.fixtures.MOCK_TOK` has promised since M0.2.
contract Deploy is Script {
    function run() external returns (MockTOK tok, A2ASettlement settlement) {
        vm.startBroadcast();
        tok = new MockTOK();
        settlement = new A2ASettlement();
        vm.stopBroadcast();

        string memory obj = "deploy";
        vm.serializeUint(obj, "v", 0);
        vm.serializeUint(obj, "chainId", block.chainid);
        vm.serializeAddress(obj, "MockTOK", address(tok));
        string memory json = vm.serializeAddress(obj, "A2ASettlement", address(settlement));
        // recursive=true is what makes this a no-op when the dir already exists
        // (false maps to fs::create_dir, which ERRORS on the second deploy).
        vm.createDir("./deployments", true);
        vm.writeJson(json, "./deployments/anvil.json");
    }
}
