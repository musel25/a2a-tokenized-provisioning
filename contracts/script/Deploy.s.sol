// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Script} from "forge-std/Script.sol";
import {Counter} from "../src/Counter.sol";

contract Deploy is Script {
    function run() external returns (Counter counter) {
        vm.startBroadcast();
        counter = new Counter();
        vm.stopBroadcast();
    }
}
