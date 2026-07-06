// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Script} from "forge-std/Script.sol";
import {Counter} from "../src/Counter.sol";

/// M1.1 lab artifact: deploys the exploration `Counter` (see contracts/EXPLORE.md), not
/// the settlement. The real deploy — MockTOK + A2ASettlement, writing
/// contracts/deployments/anvil.json — is `script/Deploy.s.sol` (M1.4); this file was
/// renamed from that path when the real one took the canonical name.
contract DeployCounter is Script {
    function run() external returns (Counter counter) {
        vm.startBroadcast();
        counter = new Counter();
        vm.stopBroadcast();
    }
}
