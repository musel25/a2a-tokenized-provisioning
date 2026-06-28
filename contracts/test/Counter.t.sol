// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Test} from "forge-std/Test.sol";
import {Counter} from "../src/Counter.sol";

contract CounterTest is Test {
    Counter internal counter;

    function setUp() public {
        counter = new Counter();
    }

    function test_startsAtZero() public view {
        assertEq(counter.number(), 0);
    }

    function test_incrementAddsOne() public {
        counter.increment();
        counter.increment();
        assertEq(counter.number(), 2);
    }

    function test_incrementEmitsEvent() public {
        vm.expectEmit(true, false, false, true);
        emit Counter.Incremented(address(this), 1);
        counter.increment();
    }
}
