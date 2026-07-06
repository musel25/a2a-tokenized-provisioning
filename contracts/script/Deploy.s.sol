// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Script} from "forge-std/Script.sol";
import {Counter} from "../src/Counter.sol";

/// M1.1 lab artifact: deploys the exploration `Counter` (see contracts/EXPLORE.md), not the
/// settlement. The real deploy script — MockTOK + A2ASettlement + deployments/anvil.json —
/// lands at M1.4.
contract Deploy is Script {
    function run() external returns (Counter counter) {
        vm.startBroadcast();
        counter = new Counter();
        vm.stopBroadcast();
    }
}
